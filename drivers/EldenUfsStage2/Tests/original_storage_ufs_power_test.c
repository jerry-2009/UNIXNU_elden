/* SPDX-License-Identifier: GPL-3.0-only */
/* Exercise device-power wake, verification and restore through the real transport. */
#include <storage_ufs.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    REG_CAP = 0x00, REG_AHIT = 0x18, REG_IS = 0x20, REG_IE = 0x24,
    REG_HCS = 0x30, REG_HCE = 0x34, REG_BASE_LO = 0x50, REG_BASE_HI = 0x54,
    REG_DOORBELL = 0x58, REG_RUN = 0x60, REG_TASK_DB = 0x78,
    REG_UIC_CMD = 0x90, REG_UIC_ARG1 = 0x94, REG_UIC_ARG2 = 0x98,
    REG_UIC_ARG3 = 0x9c
};
enum { IS_UTCS = 1, IS_UHXS = 0x20, IS_UHES = 0x40, IS_UCCS = 0x400 };
enum {
    UIC_DME_GET = 0x01, UIC_DME_HIBERN8_ENTER = 0x17,
    UIC_DME_HIBERN8_EXIT = 0x18
};
/* Linux drivers/ufs/host/ufshcd-dwc.h enum tx_fsm. */
enum { TX_HIBERN8 = 1, TX_SLEEP = 2, TX_AWAKE = 3, TX_HSBURST = 5 };
#define MPHY_TX_FSM_STATE_ARG1 0x00410000u
#define HCS_ENTRY 0x10fu
#define FW_BASE_LO 0x11110000u
#define FW_BASE_HI 2u
#define UCD_OFFSET 1024u
#define RSP_OFFSET 1536u
#define DATA_OFFSET 4096u
#define DMA_BASE UINT64_C(0x10000000)
#define ARENA_BYTES 8192u
/* A frozen timer must not remove the iteration ceiling; the power path gets a
 * 10 s deadline, so allow a generous but finite read budget. */
#define READ_CEILING 2000000u

static _Alignas(1024) unsigned char arena[ARENA_BYTES];

/* Autosense layout follows the response UPIU used by storage_ufs.c: length at
 * rsp[32], sense data at rsp[34]. Fixed 0x70/0x71 carry the key at sense[2],
 * the additional length at sense[7], and ASC/ASCQ at sense[12]/[13].
 * Descriptor 0x72/0x73 carry key/ASC/ASCQ at sense[1..3]. */
struct sense_spec {
    unsigned char format, key, asc, ascq;
    unsigned len, addlen, segment;
};
struct ssu_record { unsigned char lun, cdb[16]; };

struct fixture {
    uint32_t reg[0x304 / 4];
    uint64_t ticks;
    unsigned writes, reads, dev_syncs, cpu_syncs;
    unsigned nop_calls, query_calls, ssu_count, tur_count, cap_count, read_count;
    char log[64];
    unsigned log_len;
    uint32_t mode, entry_mode;
    unsigned fsm;
    bool manage, freeze_timer, restored;
    unsigned wake_ua_left;
    bool wake_always_ua, wake_not_ready_once, wake_not_ready_used;
    bool wake_doorbell_error, wake_no_completion, long_ssu;
    bool wake_bad_ocs, wake_bad_tag, wake_bad_lun;
    bool pretrigger_is_error;
    bool verify_query_mismatch;
    bool restore_doorbell_error, restore_query_wrong;
    unsigned query_variant, query_variant_at;
    bool raw_power_override;
    uint32_t raw_power_value;
    bool pending;
    uint64_t pending_at;
    unsigned pending_mode;
    struct sense_spec ua_sense, nr_sense, read_sense;
    struct ssu_record ssu[8];
};

static void note(struct fixture *f, char c)
{
    assert(f->log_len + 1 < sizeof(f->log));
    f->log[f->log_len++] = c;
    f->log[f->log_len] = 0;
}
static void log_reset(struct fixture *f)
{
    f->log_len = 0;
    f->log[0] = 0;
}
static uint32_t rq_bytes(const unsigned char *q)
{
    return (uint32_t)q[12] << 24 | (uint32_t)q[13] << 16 |
           (uint32_t)q[14] << 8 | q[15];
}
static bool wake_ssu(const unsigned char *q)
{
    return q[0] == 1 && q[2] == 0xd0 && q[16] == 0x1b && (q[20] >> 4) == 1;
}
static bool restore_ssu(const unsigned char *q)
{
    unsigned mode = q[20] >> 4;
    return q[0] == 1 && q[2] == 0xd0 && q[16] == 0x1b &&
           (mode == 2 || mode == 3);
}
static void ssu_ok(struct fixture *f)
{
    unsigned char *rsp = arena + RSP_OFFSET;
    memset(rsp, 0, 512);
    rsp[0] = 0x21;
    rsp[2] = 0xd0;
    arena[8] = 0;
    f->reg[REG_IS / 4] |= IS_UTCS;
    f->reg[REG_DOORBELL / 4] = 0;
}
static void maybe_complete(struct fixture *f)
{
    if (!f->pending || f->ticks < f->pending_at) return;
    f->pending = false;
    f->mode = f->pending_mode;
    ssu_ok(f);
}
static int rd32(void *ctx, uint32_t off, uint32_t *value)
{
    struct fixture *f = ctx;
    assert(off < sizeof(f->reg));
    ++f->reads;
    maybe_complete(f);
    *value = f->reg[off / 4];
    return 0;
}
static void build_sense(struct fixture *f, const struct sense_spec *s,
                        unsigned char lun)
{
    unsigned char *rsp = arena + RSP_OFFSET;
    unsigned char *sense;
    memset(rsp, 0, 512);
    rsp[0] = 0x21;
    rsp[2] = lun;
    rsp[6] = 1;
    rsp[7] = 2;
    rsp[10] = (unsigned char)(s->segment >> 8);
    rsp[11] = (unsigned char)s->segment;
    rsp[32] = (unsigned char)(s->len >> 8);
    rsp[33] = (unsigned char)s->len;
    sense = rsp + 34;
    sense[0] = s->format;
    if (s->format == 0x72 || s->format == 0x73) {
        sense[1] = s->key;
        sense[2] = s->asc;
        sense[3] = s->ascq;
    } else {
        sense[2] = s->key;
        sense[7] = (unsigned char)s->addlen;
        sense[12] = s->asc;
        sense[13] = s->ascq;
    }
    arena[8] = 0;
    f->reg[REG_IS / 4] |= IS_UTCS;
    f->reg[REG_DOORBELL / 4] = 0;
}
/* The SSU contract: device WLUN 0xd0, CDB[0]=0x1b, CDB[4]=mode<<4, every other
 * CDB byte zero, no expected data and no PRDT entry. */
static unsigned record_ssu(struct fixture *f, const unsigned char *q)
{
    const unsigned char *cdb = q + 16;
    unsigned mode = cdb[4] >> 4;

    assert(q[0] == 1 && q[2] == 0xd0 && q[3] == 0);
    assert(q[1] == 0);
    assert(q[12] == 0 && q[13] == 0 && q[14] == 0 && q[15] == 0);
    assert(arena[28] == 0 && arena[29] == 0);
    assert(cdb[0] == 0x1b);
    assert(mode == 1 || mode == 2 || mode == 3);
    for (unsigned i = 0; i < 16; ++i) {
        if (i == 0)
            assert(cdb[i] == 0x1b);
        else if (i == 4)
            assert(cdb[i] == (unsigned char)(mode << 4));
        else
            assert(cdb[i] == 0);
    }
    assert(f->ssu_count < sizeof(f->ssu) / sizeof(f->ssu[0]));
    f->ssu[f->ssu_count].lun = q[2];
    memcpy(f->ssu[f->ssu_count].cdb, cdb, 16);
    ++f->ssu_count;
    return mode;
}
static void ssu_outcome(struct fixture *f, unsigned mode)
{
    if (mode == 1) {
        if (f->wake_no_completion) {
            f->pending = true;
            f->pending_at = UINT64_MAX;
            f->pending_mode = 1;
            f->reg[REG_DOORBELL / 4] = 1;
            return;
        }
        if (f->wake_always_ua) {
            build_sense(f, &f->ua_sense, 0xd0);
            return;
        }
        if (f->wake_ua_left) {
            --f->wake_ua_left;
            build_sense(f, &f->ua_sense, 0xd0);
            return;
        }
        if (f->wake_not_ready_once && !f->wake_not_ready_used) {
            f->wake_not_ready_used = true;
            build_sense(f, &f->nr_sense, 0xd0);
            return;
        }
        if (f->wake_bad_ocs) {
            unsigned char *rsp = arena + RSP_OFFSET;
            memset(rsp, 0, 512);
            rsp[0] = 0x21;
            rsp[2] = 0xd0;
            arena[8] = 1; /* OCS failed: completion is not known-good. */
            f->reg[REG_IS / 4] |= IS_UTCS;
            f->reg[REG_DOORBELL / 4] = 0;
            return;
        }
        if (f->wake_bad_tag) {
            unsigned char *rsp = arena + RSP_OFFSET;
            f->mode = 1;
            memset(rsp, 0, 512);
            rsp[0] = 0x21;
            rsp[2] = 0xd0;
            rsp[3] = 1;
            arena[8] = 0;
            f->reg[REG_IS / 4] |= IS_UTCS;
            f->reg[REG_DOORBELL / 4] = 0;
            return;
        }
        if (f->wake_bad_lun) {
            unsigned char *rsp = arena + RSP_OFFSET;
            f->mode = 1;
            memset(rsp, 0, 512);
            rsp[0] = 0x21;
            rsp[2] = 0;
            arena[8] = 0;
            f->reg[REG_IS / 4] |= IS_UTCS;
            f->reg[REG_DOORBELL / 4] = 0;
            return;
        }
        if (f->long_ssu) {
            f->pending = true;
            f->pending_at = f->ticks + 5000; /* 5 s, below the 10 s bound. */
            f->pending_mode = 1;
            f->reg[REG_DOORBELL / 4] = 1;
            return;
        }
        f->mode = 1;
        ssu_ok(f);
        return;
    }
    f->mode = mode;
    f->restored = true;
    ssu_ok(f);
}
/* The device attribute and the SSU power condition have DIFFERENT encodings.
 * This independent fixture mapping matches the UFS attribute, including the
 * UFS value 0x33 (POWERDOWN). Internal fake modes remain SSU 1/2/3. */
static uint32_t attribute_mode(uint32_t mode)
{
    switch(mode){case 1:return 0x11;case 2:return 0x22;case 3:return 0x33;}
    return mode;
}
static void query(struct fixture *f, const unsigned char *q)
{
    unsigned char *rsp = arena + RSP_OFFSET;
    uint32_t value;

    ++f->query_calls;
    assert(q[2] == 0 && q[3] == 0 && q[5] == 1);
    if (q[12] == 1) { /* existing READ DESCRIPTOR path stays unchanged */
        memset(rsp, 0, 512);
        rsp[0] = 0x36;
        memcpy(rsp + 12, q + 12, 20);
        rsp[10] = 0;
        rsp[11] = 4;
        rsp[18] = 0;
        rsp[19] = 4;
        rsp[32] = 4;
        rsp[33] = q[13];
        rsp[34] = q[14];
        rsp[35] = 0x5a;
        arena[8] = 0;
        f->reg[REG_IS / 4] |= IS_UTCS;
        f->reg[REG_DOORBELL / 4] = 0;
        return;
    }
    /* READ ATTRIBUTE, bCurrentPowerMode (IDN 2), index/selector 0, no data. */
    assert(q[12] == 3 && q[13] == 2 && q[14] == 0 && q[15] == 0);
    assert(q[18] == 0 && q[19] == 0);
    assert(arena[28] == 0 && arena[29] == 0);
    if (f->query_calls == 1)
        value = f->entry_mode;
    else if (f->query_calls == 2 && f->verify_query_mismatch)
        value = f->entry_mode;
    else if (f->restored && f->restore_query_wrong)
        value = 1;
    else
        value = f->mode;
    value = f->raw_power_override ? f->raw_power_value : attribute_mode(value);
    memset(rsp, 0, 512);
    rsp[0] = 0x36; /* QUERY RESPONSE */
    rsp[12] = 3;
    rsp[13] = 2;
    rsp[14] = 0;
    rsp[15] = 0;
    rsp[20] = (unsigned char)(value >> 24);
    rsp[21] = (unsigned char)(value >> 16);
    rsp[22] = (unsigned char)(value >> 8);
    rsp[23] = (unsigned char)value;
    if (f->query_variant_at == f->query_calls) {
        if (f->query_variant & 1) rsp[12] = 1;
        if (f->query_variant & 2) rsp[13] = 1;
        if (f->query_variant & 4) rsp[15] = 1;
        if (f->query_variant & 8) rsp[19] = 1;
        if (f->query_variant & 16) rsp[11] = 1;
        if (f->query_variant & 32) rsp[6] = 1;
        if (f->query_variant & 64) rsp[3] = 1;
    }
    arena[8] = 0;
    f->reg[REG_IS / 4] |= IS_UTCS;
    f->reg[REG_DOORBELL / 4] = 0;
}
static void doorbell(struct fixture *f, const unsigned char *q)
{
    unsigned char *rsp = arena + RSP_OFFSET;
    const unsigned char *cdb;

    if (q[0] == 0) {
        note(f, 'N');
        ++f->nop_calls;
        memset(rsp, 0, 512);
        rsp[0] = 0x20;
        arena[8] = 0;
        f->reg[REG_IS / 4] |= IS_UTCS;
        f->reg[REG_DOORBELL / 4] = 0;
        return;
    }
    if (q[0] == 0x16) {
        note(f, 'Q');
        query(f, q);
        return;
    }
    assert(q[0] == 1);
    cdb = q + 16;
    if (cdb[0] == 0x1b) {
        note(f, 'S');
        ssu_outcome(f, record_ssu(f, q));
        return;
    }
    if (cdb[0] == 0x00) {
        note(f, 'T');
        ++f->tur_count;
        memset(rsp, 0, 512);
        rsp[0] = 0x21;
        rsp[2] = q[2];
        arena[8] = 0;
        f->reg[REG_IS / 4] |= IS_UTCS;
        f->reg[REG_DOORBELL / 4] = 0;
        return;
    }
    if (cdb[0] == 0x9e) {
        note(f, 'C');
        ++f->cap_count;
        assert(q[1] == 0x40 && rq_bytes(q) == 32);
        memset(arena + DATA_OFFSET, 0, 32);
        arena[DATA_OFFSET + 6] = 0x07; /* last LBA 2047 */
        arena[DATA_OFFSET + 7] = 0xff;
        arena[DATA_OFFSET + 10] = 0x02; /* block size 512 */
        arena[DATA_OFFSET + 11] = 0x00;
        memset(rsp, 0, 512);
        rsp[0] = 0x21;
        rsp[2] = q[2];
        arena[8] = 0;
        f->reg[REG_IS / 4] |= IS_UTCS;
        f->reg[REG_DOORBELL / 4] = 0;
        return;
    }
    if (cdb[0] == 0x88) {
        note(f, 'B');
        ++f->read_count;
        assert(q[1] == 0x40 && rq_bytes(q) == 512);
        if (f->read_sense.format) {
            build_sense(f, &f->read_sense, q[2]);
            return;
        }
        memset(arena + DATA_OFFSET, 0x5a, 512);
        memset(rsp, 0, 512);
        rsp[0] = 0x21;
        rsp[2] = q[2];
        arena[8] = 0;
        f->reg[REG_IS / 4] |= IS_UTCS;
        f->reg[REG_DOORBELL / 4] = 0;
        return;
    }
    /* No block write, SYNCHRONIZE CACHE or other command may be emitted. */
    assert(0 && "forbidden SCSI command");
}
static void uic(struct fixture *f, uint32_t cmd)
{
    assert(f->reg[REG_DOORBELL / 4] == 0);
    assert(f->reg[REG_TASK_DB / 4] == 0);
    assert((f->reg[REG_RUN / 4] & 1u) == 0);
    if (cmd == UIC_DME_GET) {
        assert(f->reg[REG_UIC_ARG1 / 4] == MPHY_TX_FSM_STATE_ARG1);
        assert(f->reg[REG_UIC_ARG2 / 4] == 0);
        assert(f->reg[REG_UIC_ARG3 / 4] == 0);
        note(f, 'G');
        f->reg[REG_UIC_ARG2 / 4] = 0;
        f->reg[REG_UIC_ARG3 / 4] = f->fsm;
        f->reg[REG_IS / 4] |= IS_UCCS;
        return;
    }
    if (cmd == UIC_DME_HIBERN8_EXIT) {
        assert(f->reg[REG_UIC_ARG1 / 4] == 0);
        assert(f->fsm == TX_HIBERN8);
        note(f, 'X');
        f->fsm = TX_AWAKE;
        f->reg[REG_IS / 4] |= IS_UCCS | IS_UHXS;
        f->reg[REG_HCS / 4] = (f->reg[REG_HCS / 4] & ~0x700u) | (1u << 8);
        f->reg[REG_UIC_ARG2 / 4] = 0;
        return;
    }
    assert(cmd == UIC_DME_HIBERN8_ENTER);
    assert(f->reg[REG_UIC_ARG1 / 4] == 0);
    assert(f->fsm >= TX_SLEEP && f->fsm <= TX_HSBURST);
    note(f, 'E');
    f->fsm = TX_HIBERN8;
    f->reg[REG_IS / 4] |= IS_UCCS | IS_UHES;
    f->reg[REG_HCS / 4] = (f->reg[REG_HCS / 4] & ~0x700u) | (1u << 8);
    f->reg[REG_UIC_ARG2 / 4] = 0;
}
static int wr32(void *ctx, uint32_t off, uint32_t value)
{
    struct fixture *f = ctx;
    const unsigned char *q = arena + UCD_OFFSET;

    ++f->writes;
    assert(off < sizeof(f->reg));
    switch (off) {
    case REG_IE:
    case REG_AHIT:
    case REG_BASE_LO:
    case REG_BASE_HI:
    case REG_UIC_ARG1:
    case REG_UIC_ARG2:
    case REG_UIC_ARG3:
        f->reg[off / 4] = value;
        return 0;
    case REG_RUN:
        f->reg[off / 4] = value;
        if (value & 1u)
            f->reg[REG_HCS / 4] |= 0x6u;
        else {
            f->reg[REG_HCS / 4] &= ~0x6u;
            note(f, 'r');
        }
        return 0;
    case REG_IS:
        /* A failure before the SSU doorbell is a preflight fault: no trigger,
         * therefore no restoration obligation. */
        if (f->pretrigger_is_error && wake_ssu(q)) {
            f->pretrigger_is_error = false;
            return 1;
        }
        f->reg[REG_IS / 4] &= ~value;
        return 0;
    case REG_DOORBELL:
        assert(value == 1);
        /* The callback may fail after the write took effect: record the SSU
         * attempt, then report the transport error. */
        if (f->wake_doorbell_error && wake_ssu(q)) {
            note(f, 'S');
            record_ssu(f, q);
            f->wake_doorbell_error = false;
            return 1;
        }
        if (f->restore_doorbell_error && restore_ssu(q)) {
            note(f, 'S');
            record_ssu(f, q);
            f->restore_doorbell_error = false;
            return 1;
        }
        f->reg[REG_DOORBELL / 4] = 1;
        doorbell(f, q);
        return 0;
    case REG_UIC_CMD:
        uic(f, value);
        return 0;
    }
    assert(0 && "write outside the allowed register set");
    return 0;
}
static void dev_sync(void *ctx, void *buffer, size_t bytes)
{
    struct fixture *f = ctx;
    assert(buffer == arena && bytes == ARENA_BYTES);
    ++f->dev_syncs;
}
static void cpu_sync(void *ctx, void *buffer, size_t bytes)
{
    struct fixture *f = ctx;
    assert(buffer == arena && bytes == ARENA_BYTES);
    ++f->cpu_syncs;
}
static uint64_t now_ms(void *ctx)
{
    struct fixture *f = ctx;
    return f->freeze_timer ? 0 : f->ticks;
}
static void delay_us(void *ctx, uint32_t us)
{
    struct fixture *f = ctx;
    f->ticks += (us + 999) / 1000;
}
static struct kshim_ufs_ops ops_of(struct fixture *f)
{
    struct kshim_ufs_ops o = {f, rd32, wr32, dev_sync, cpu_sync, now_ms,
                               delay_us, f->manage};
    return o;
}
static void init(struct fixture *f, uint32_t entry)
{
    memset(f, 0, sizeof(*f));
    memset(arena, 0, sizeof(arena));
    f->mode = entry;
    f->entry_mode = entry;
    f->fsm = TX_HIBERN8;
    f->reg[REG_CAP / 4] = 1u << 24; /* 64-bit addressing */
    f->reg[REG_HCE / 4] = 1;
    f->reg[REG_HCS / 4] = HCS_ENTRY;
    f->reg[REG_BASE_LO / 4] = FW_BASE_LO;
    f->reg[REG_BASE_HI / 4] = FW_BASE_HI;
    f->reg[REG_RUN / 4] = 1;
    f->reg[REG_IE / 4] = 0x400;
    f->reg[REG_AHIT / 4] = 0x123;
    f->reg[REG_IS / 4] = IS_UCCS; /* stale firmware completion */
    f->ua_sense = (struct sense_spec){0x70, 6, 0x29, 0x00, 18, 0x0a, 20};
    f->nr_sense = (struct sense_spec){0x70, 2, 0x04, 0x02, 18, 0x0a, 20};
}
static void claim(struct fixture *f, struct kshim_ufs_host *h)
{
    struct kshim_ufs_ops o = ops_of(f);
    memset(h, 0, sizeof(*h));
    assert(kshim_ufs_claim(h, &o, arena, sizeof(arena), DMA_BASE) == 0);
}
static void assert_restored(const struct fixture *f)
{
    assert(f->reg[REG_BASE_LO / 4] == FW_BASE_LO);
    assert(f->reg[REG_BASE_HI / 4] == FW_BASE_HI);
    assert(f->reg[REG_RUN / 4] == 1);
    assert(f->reg[REG_IE / 4] == 0x400);
    assert(f->reg[REG_AHIT / 4] == 0x123);
}
static void assert_ssu_record(const struct fixture *f, unsigned i,
                              unsigned mode)
{
    assert(i < f->ssu_count);
    assert(f->ssu[i].lun == 0xd0);
    for (unsigned j = 0; j < 16; ++j) {
        if (j == 0)
            assert(f->ssu[i].cdb[j] == 0x1b);
        else if (j == 4)
            assert(f->ssu[i].cdb[j] == (unsigned char)(mode << 4));
        else
            assert(f->ssu[i].cdb[j] == 0);
    }
}
static void read_one(struct kshim_ufs_lun *l, unsigned char *buf)
{
    assert(kshim_block_read(&l->block, 0, 1, buf) == 0);
    assert(buf[0] == 0x5a && buf[511] == 0x5a);
}
static void wait_for_release_ownership(const struct fixture *f,
                                       const struct kshim_ufs_host *h)
{
    assert(h->owned == 1);
    assert(f->reg[REG_BASE_LO / 4] == (uint32_t)DMA_BASE);
    assert(f->reg[REG_BASE_HI / 4] == 0);
}

/* Ordinary claim/NOP/open_lun must never touch device power, even when the
 * device is asleep, and release must then hand the firmware state back. */
static void test_claim_and_open_lun_do_not_touch_power(void)
{
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_lun l;

    init(&f, 2);
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_open_lun(&h, 0, false, &l) == 0);
    assert(f.query_calls == 0 && f.ssu_count == 0);
    assert(h.power.phase == 0 && h.power.restore_mode == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.query_calls == 0 && f.ssu_count == 0);
    assert_restored(&f);
    assert(h.owned == 0);
}

/* ACTIVE is already usable: one query, no SSU, no extra query. */
static void test_active_entry_no_power(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 1);
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == 0);
    assert(f.query_calls == 1 && f.ssu_count == 0);
    assert(h.power.initial_mode == 0x11 && h.power.current_mode == 0x11);
    assert(h.power.restore_mode == 0 && h.power.uncertain == 0);
    assert(h.power.phase == 1);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.query_calls == 1 && f.ssu_count == 0);
    assert(h.power.restore_mode == 0);
    assert_restored(&f);
    assert(h.owned == 0);
}

/* SLEEP and POWERDOWN: SSU on the device WLUN, verify ACTIVE, do real capacity
 * and block reads, then restore the entry mode before cleaning up. */
static void test_wake_sleep_and_powerdown(void)
{
    static const uint32_t modes[] = {2, 3};

    for (unsigned i = 0; i < 2; ++i) {
        struct fixture f;
        struct kshim_ufs_host h;
        struct kshim_ufs_lun l;
        unsigned char buf[512];

        init(&f, modes[i]);
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        log_reset(&f);
        assert(kshim_ufs_prepare_device(&h) == 0);
        assert(f.ssu_count == 1 && f.query_calls == 2);
        assert_ssu_record(&f, 0, 1);
        assert(f.mode == 1);
        assert(h.power.initial_mode == attribute_mode(modes[i]));
        assert(h.power.current_mode == 0x11);
        assert(h.power.restore_mode == modes[i]);
        assert(h.power.uncertain == 0 && h.power.phase == 3);
        assert(kshim_ufs_open_lun(&h, 0, false, &l) == 0);
        read_one(&l, buf);
        assert(kshim_ufs_release(&h) == 0);
        assert(f.ssu_count == 2 && f.query_calls == 4);
        assert_ssu_record(&f, 1, modes[i]);
        assert(f.mode == modes[i]);
        assert(h.power.current_mode == attribute_mode(modes[i]));
        assert(h.power.restore_mode == 0 && h.power.phase == 7);
        assert(h.power.uncertain == 0);
        assert_restored(&f);
        assert(h.owned == 0);
        /* Query, wake SSU, verify, TUR, capacity, block read, then release:
         * current query, restore SSU, verify, and only then the list stop. */
        assert(strcmp(f.log, "QSQTCBQSQr") == 0);
    }
}

/* Every malformed READ ATTRIBUTE response is rejected before any SSU. */
static void test_malformed_initial_query(void)
{
    static const unsigned variants[] = {1, 2, 4, 8, 16, 32, 64};

    for (unsigned i = 0; i < sizeof(variants) / sizeof(variants[0]); ++i) {
        struct fixture f;
        struct kshim_ufs_host h;

        init(&f, 2);
        f.query_variant = variants[i];
        f.query_variant_at = 1;
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_prepare_device(&h) != 0);
        assert(f.ssu_count == 0);
        assert(h.power.initial_mode == UINT32_MAX);
        assert(h.power.current_mode == UINT32_MAX);
        assert(h.power.restore_mode == 0 && h.power.uncertain == 0);
        /* The query completed, so the ordinary firmware handoff survives. */
        assert(kshim_ufs_release(&h) == 0);
        assert(f.ssu_count == 0);
        assert_restored(&f);
        assert(h.owned == 0);
    }
}

/* Unknown modes, including a full word with high bits set, are refused
 * without any power command. */
static void test_unknown_entry_mode(void)
{
    static const uint32_t modes[] = {0, 4, 255, 0x01000002u};

    for (unsigned i = 0; i < sizeof(modes) / sizeof(modes[0]); ++i) {
        struct fixture f;
        struct kshim_ufs_host h;

        init(&f, modes[i]);
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_prepare_device(&h) == KSHIM_UFS_UNSUPPORTED);
        assert(f.ssu_count == 0);
        assert(h.power.restore_mode == 0 && h.power.uncertain == 0);
        assert(kshim_ufs_release(&h) == 0);
        assert(f.ssu_count == 0);
        assert_restored(&f);
        assert(h.owned == 0);
    }
}

/* UNIT ATTENTION on the wake SSU is retried once and then succeeds. */
static void test_ssu_unit_attention_then_good(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_ua_left = 1;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == 0);
    assert(f.ssu_count == 2 && f.query_calls == 2);
    assert_ssu_record(&f, 0, 1);
    assert_ssu_record(&f, 1, 1);
    assert(f.mode == 1);
    assert(h.power.current_mode == 0x11 && h.power.restore_mode == 2);
    assert(h.power.uncertain == 0 && h.power.phase == 3);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 3 && f.query_calls == 4);
    assert_ssu_record(&f, 2, 2);
    assert(h.power.restore_mode == 0 && h.power.phase == 7);
    assert(f.mode == 2);
    assert_restored(&f);
}

/* Persistent UNIT ATTENTION is bounded at three SSUs. The failed wake did
 * nothing to the device, so release can clear the obligation by querying the
 * original mode, without a restore SSU. */
static void test_ssu_persistent_unit_attention(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_always_ua = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.ssu_count == 3 && f.query_calls == 1);
    assert(h.power.uncertain == 0 && h.power.restore_mode == 2);
    assert(h.power.phase == 2);
    /* The failing command is still visible to the caller. */
    assert(h.last_scsi_opcode == 0x1b && h.last_scsi_lun == 0xd0);
    assert(h.last_scsi_status == 2 && h.last_sense_key == 6);
    assert(h.last_sense_valid == 3);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 3 && f.query_calls == 2);
    assert(h.power.restore_mode == 0);
    assert(f.mode == 2);
    assert_restored(&f);
}

/* NOT READY is not a retry condition: exactly one SSU. */
static void test_ssu_not_ready_not_retried(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_not_ready_once = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.ssu_count == 1 && f.query_calls == 1);
    assert(h.power.uncertain == 0 && h.power.restore_mode == 2);
    assert(h.last_scsi_opcode == 0x1b && h.last_scsi_lun == 0xd0);
    assert(h.last_scsi_status == 2 && h.last_sense_key == 2);
    assert(h.last_sense_asc == 0x04 && h.last_sense_ascq == 0x02);
    assert(h.last_sense_valid == 3);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    assert(h.power.restore_mode == 0);
    assert_restored(&f);
}

/* A CHECK CONDITION whose sense cannot be parsed has no valid key6 UNIT
 * ATTENTION, so it is not retried; the completion is still valid and owes a
 * restore. */
static void test_ssu_malformed_sense_not_retried(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_not_ready_once = true;
    f.nr_sense.key = 6;
    f.nr_sense.asc = 0x29;
    f.nr_sense.ascq = 0;
    f.nr_sense.len = 0;
    f.nr_sense.segment = 0;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.ssu_count == 1);
    assert(h.last_scsi_status == 2);
    assert(h.last_sense_valid == 0);
    assert(h.power.uncertain == 0 && h.power.restore_mode == 2);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    assert(h.power.restore_mode == 0);
    assert_restored(&f);
}

/* The wake SSU took effect but the verification query reports the old mode:
 * the caller sees an error and release puts the real original mode back. */
static void test_verify_mismatch_restores_original(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.verify_query_mismatch = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    assert(f.mode == 1); /* the device really did wake */
    assert(h.power.uncertain == 0 && h.power.restore_mode == 2);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 2 && f.query_calls == 4);
    assert_ssu_record(&f, 1, 2);
    assert(f.mode == 2);
    assert(h.power.restore_mode == 0);
    assert_restored(&f);
    assert(h.owned == 0);
}

/* A malformed verification query is the same obligation: error to the caller,
 * but release still restores (or fails). */
static void test_verify_query_failure_restores_original(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.query_variant_at = 2;
    f.query_variant = 32; /* response=1 with status 0 */
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    assert(f.mode == 1);
    assert(h.power.restore_mode == 2 && h.power.uncertain == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 2 && f.query_calls == 4);
    assert_ssu_record(&f, 1, 2);
    assert(f.mode == 2);
    assert(h.power.restore_mode == 0);
    assert_restored(&f);
}

/* A fault before the SSU doorbell leaves no obligation, because the command
 * was never triggered. */
static void test_pre_trigger_ssu_failure_owes_nothing(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.pretrigger_is_error = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == KSHIM_STORAGE_IO);
    assert(f.ssu_count == 0);
    assert(h.power.restore_mode == 0 && h.power.uncertain == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.ssu_count == 0 && f.query_calls == 1);
    assert_restored(&f);
    assert(h.owned == 0);
}

/* A failed doorbell callback may still have queued the SSU: the obligation is
 * retained, release quarantines and never writes the firmware base. */
static void test_ssu_trigger_error_quarantines(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_doorbell_error = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == KSHIM_STORAGE_IO);
    assert(f.ssu_count == 1 && f.query_calls == 1);
    assert(h.power.restore_mode == 2 && h.power.uncertain == 1);
    assert(kshim_ufs_release(&h) != 0);
    wait_for_release_ownership(&f, &h);
    assert(h.power.restore_mode == 2);
    assert(f.query_calls == 1);
}

/* A completion with bad OCS, tag or LUN is not known-good: uncertain stays,
 * so release cannot hand the controller back. */
static void test_invalid_ssu_completion_quarantines(void)
{
    for (unsigned i = 0; i < 3; ++i) {
        struct fixture f;
        struct kshim_ufs_host h;

        init(&f, 2);
        if (i == 0) f.wake_bad_ocs = true;
        if (i == 1) f.wake_bad_tag = true;
        if (i == 2) f.wake_bad_lun = true;
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_prepare_device(&h) != 0);
        assert(f.ssu_count == 1 && f.query_calls == 1);
        assert(h.power.restore_mode == 2 && h.power.uncertain == 1);
        assert(kshim_ufs_release(&h) != 0);
        wait_for_release_ownership(&f, &h);
        assert(h.power.restore_mode == 2);
    }
}

/* Frozen clock and no SSU completion: the iteration bound terminates the wait
 * and the unknown outcome is quarantined. */
static void test_ssu_timeout_bounded(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.wake_no_completion = true;
    f.freeze_timer = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) != 0);
    assert(f.reads <= READ_CEILING);
    assert(f.ssu_count == 1);
    assert(h.power.restore_mode == 2 && h.power.uncertain == 1);
    assert(kshim_ufs_release(&h) != 0);
    wait_for_release_ownership(&f, &h);
    assert(h.power.restore_mode == 2);
}

/* The power command has a 10 s deadline, not the ordinary 1 s: a wake that
 * takes 5 s still succeeds. */
static void test_long_ssu_completes(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    f.long_ssu = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == 0);
    assert(f.ticks >= 5000 && f.ticks < 10000);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    assert(f.mode == 1);
    assert(h.power.current_mode == 0x11 && h.power.restore_mode == 2);
    assert(h.power.uncertain == 0 && h.power.phase == 3);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.mode == 2 && h.power.phase == 7);
    assert_restored(&f);
}

/* A restore SSU whose doorbell callback fails keeps ownership and leaves the
 * firmware base untouched. */
static void test_restore_ssu_failure_retains_ownership(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == 0);
    f.restore_doorbell_error = true;
    assert(kshim_ufs_release(&h) != 0);
    assert(f.ssu_count == 2);
    assert_ssu_record(&f, 1, 2);
    assert(f.query_calls == 3);
    assert(h.power.restore_mode == 2 && h.power.uncertain == 1);
    wait_for_release_ownership(&f, &h);
}

/* A restore that is not confirmed by the exact original mode is a release
 * failure: no firmware handoff. */
static void test_restore_verify_mismatch_retains_ownership(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f, 2);
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_prepare_device(&h) == 0);
    f.restore_query_wrong = true;
    assert(kshim_ufs_release(&h) != 0);
    assert(f.ssu_count == 2 && f.query_calls == 4);
    assert(f.mode == 2);
    assert(h.power.restore_mode == 2 && h.power.uncertain == 0);
    wait_for_release_ownership(&f, &h);
}

/* Fixed and descriptor autosense expose key, ASC and ASCQ; the opcode/LUN are
 * the last submitted SCSI command and a descriptor query does not replace
 * them. A fixed sense whose additional-length byte does not cover ASC/ASCQ
 * keeps only the key valid. */
static void test_diagnostics_on_read_failure(void)
{
    static const struct sense_spec specs[] = {
        {0x70, 2, 0x04, 0x02, 18, 0x0a, 20},
        {0x71, 2, 0x04, 0x02, 18, 0x0a, 20},
        {0x72, 2, 0x04, 0x02, 8, 0, 10},
        {0x73, 2, 0x04, 0x02, 8, 0, 10},
    };

    for (unsigned i = 0; i < sizeof(specs) / sizeof(specs[0]); ++i) {
        struct fixture f;
        struct kshim_ufs_host h;
        struct kshim_ufs_lun l;
        unsigned char desc[32];
        unsigned char buf[512];
        uint16_t length = (uint16_t)sizeof(desc);

        init(&f, 1);
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_prepare_device(&h) == 0);
        assert(kshim_ufs_open_lun(&h, 0, false, &l) == 0);
        assert(h.last_scsi_opcode == 0x9e && h.last_scsi_lun == 0);
        assert(h.last_sense_valid == 0);
        /* The descriptor query must keep working and must not become the
         * command identified by the diagnostics. */
        assert(kshim_ufs_read_descriptor(&h, 0, 0, desc, &length) == 0);
        assert(length == 4 && desc[0] == 4);
        assert(h.last_scsi_opcode == 0x9e && h.last_scsi_lun == 0);
        assert(h.last_sense_valid == 0);
        f.read_sense = specs[i];
        /* The public block layer normalizes transport errors to IO. */
        assert(kshim_block_read(&l.block, 0, 1, buf) == KSHIM_STORAGE_IO);
        assert(h.last_scsi_opcode == 0x88 && h.last_scsi_lun == 0);
        assert(h.last_scsi_status == 2 && h.last_sense_key == 2);
        assert(h.last_sense_asc == 0x04 && h.last_sense_ascq == 0x02);
        assert(h.last_sense_valid == 3);
        /* The next completed transfer clears status/key/ASC validity. */
        f.read_sense = (struct sense_spec){0, 0, 0, 0, 0, 0, 0};
        memset(buf, 0, sizeof(buf));
        assert(kshim_block_read(&l.block, 0, 1, buf) == 0);
        assert(buf[0] == 0x5a && buf[511] == 0x5a);
        assert(h.last_scsi_status == 0 && h.last_sense_key == 0);
        assert(h.last_sense_valid == 0);
        assert(h.last_sense_asc == 0 && h.last_sense_ascq == 0);
        assert(kshim_ufs_release(&h) == 0);
        assert_restored(&f);
    }

    /* Fixed 0x70, declared length 18, but the additional-length byte covers
     * only eight bytes: the key is valid, ASC/ASCQ are not. */
    {
        struct fixture f;
        struct kshim_ufs_host h;

        init(&f, 2);
        f.wake_not_ready_once = true;
        f.nr_sense.addlen = 0;
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_prepare_device(&h) != 0);
        assert(f.ssu_count == 1);
        assert(h.last_scsi_status == 2 && h.last_sense_key == 2);
        assert(h.last_sense_valid == 1);
        assert(h.last_sense_asc == 0 && h.last_sense_ascq == 0);
        assert(kshim_ufs_release(&h) == 0);
        assert_restored(&f);
    }

    /* The declared length itself must cover the ASC/ASCQ bytes: fixed needs
     * 14, descriptor needs 4. Both keep only the key. */
    {
        static const struct {
            unsigned char format;
            unsigned len, segment;
        } short_sense[] = {
            {0x70, 13, 15}, /* fixed: ASCQ at sense[13] is outside n=13 */
            {0x72, 3, 5},   /* descriptor: ASCQ at sense[3] is outside n=3 */
        };

        for (unsigned i = 0; i < sizeof(short_sense) / sizeof(short_sense[0]);
             ++i) {
            struct fixture f;
            struct kshim_ufs_host h;

            init(&f, 2);
            f.wake_not_ready_once = true;
            f.nr_sense.format = short_sense[i].format;
            f.nr_sense.len = short_sense[i].len;
            f.nr_sense.segment = short_sense[i].segment;
            claim(&f, &h);
            assert(kshim_ufs_nop(&h) == 0);
            assert(kshim_ufs_prepare_device(&h) != 0);
            assert(f.ssu_count == 1);
            assert(h.last_scsi_status == 2 && h.last_sense_key == 2);
            assert(h.last_sense_valid == 1);
            assert(h.last_sense_asc == 0 && h.last_sense_ascq == 0);
            assert(kshim_ufs_release(&h) == 0);
            assert_restored(&f);
        }
    }
}

/* Optional combined case: power restore happens before the list stop and the
 * HIBERN8 re-entry, so the existing link restore sees the same link it would
 * have seen without the power work. */
static void test_manage_link_combined_order(void)
{
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_lun l;
    unsigned char buf[512];

    init(&f, 2);
    f.manage = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(f.fsm == TX_AWAKE);
    log_reset(&f);
    assert(kshim_ufs_prepare_device(&h) == 0);
    assert(kshim_ufs_open_lun(&h, 0, false, &l) == 0);
    read_one(&l, buf);
    assert(f.ssu_count == 1 && f.query_calls == 2);
    log_reset(&f);
    assert(kshim_ufs_release(&h) == 0);
    assert(strcmp(f.log, "QSQrEG") == 0);
    assert(f.ssu_count == 2 && f.query_calls == 4);
    assert_ssu_record(&f, 0, 1);
    assert_ssu_record(&f, 1, 2);
    assert(f.mode == 2);
    assert(f.fsm == TX_HIBERN8);
    assert(h.power.phase == 7 && h.power.restore_mode == 0);
    assert(h.link.restore_hibern8 == 0 && h.link.uncertain == 0);
    assert_restored(&f);
    assert(h.owned == 0);
}

static void test_raw_transitional_and_command_values_rejected(void)
{
    const uint32_t bad[]={1,2,3,0x10,0x20,0x30,0x21,0x44,0x10000033};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i){
        struct fixture f;struct kshim_ufs_host h;
        init(&f,1);f.raw_power_override=true;f.raw_power_value=bad[i];
        claim(&f,&h);assert(kshim_ufs_nop(&h)==0);
        assert(kshim_ufs_prepare_device(&h)==KSHIM_UFS_UNSUPPORTED);
        assert(h.power.initial_mode==bad[i] && h.power.current_mode==bad[i]);
        assert(f.ssu_count==0 && h.power.restore_mode==0);
        assert(kshim_ufs_release(&h)==0);assert_restored(&f);
    }
}
int main(void)
{
    test_raw_transitional_and_command_values_rejected();
    test_claim_and_open_lun_do_not_touch_power();
    test_active_entry_no_power();
    test_wake_sleep_and_powerdown();
    test_malformed_initial_query();
    test_unknown_entry_mode();
    test_ssu_unit_attention_then_good();
    test_ssu_persistent_unit_attention();
    test_ssu_not_ready_not_retried();
    test_ssu_malformed_sense_not_retried();
    test_verify_mismatch_restores_original();
    test_verify_query_failure_restores_original();
    test_pre_trigger_ssu_failure_owes_nothing();
    test_ssu_trigger_error_quarantines();
    test_invalid_ssu_completion_quarantines();
    test_ssu_timeout_bounded();
    test_long_ssu_completes();
    test_restore_ssu_failure_retains_ownership();
    test_restore_verify_mismatch_retains_ownership();
    test_diagnostics_on_read_failure();
    test_manage_link_combined_order();
    puts("storage_ufs_power_test: device power prepare/restore contract: PASS");
    return 0;
}
