/* SPDX-License-Identifier: GPL-3.0-only */
/* Exercise inherited HIBERN8 wake and restore using MMIO controller semantics. */
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
enum {
    UIC_DME_GET = 0x01, UIC_DME_HIBERN8_ENTER = 0x17,
    UIC_DME_HIBERN8_EXIT = 0x18
};
enum { IS_UTCS = 1, IS_UHXS = 0x20, IS_UHES = 0x40, IS_UCCS = 0x400 };
/* Linux drivers/ufs/host/ufshcd-dwc.h enum tx_fsm: 0 DISABLED, 1 HIBERN8,
 * 2 SLEEP, 3 STALL, 4 LSBURST, 5 HSBURST. 3 was the only awake value this
 * part showed at first; 2, 4 and 5 are equally normal awake states and must
 * be accepted, while 0, 6 and 0xff remain unknown. */
enum { TX_FSM_DISABLED = 0, TX_FSM_HIBERN8 = 1, TX_FSM_SLEEP = 2,
       TX_FSM_AWAKE = 3 /* STALL */, TX_FSM_LSBURST = 4, TX_FSM_HSBURST = 5 };
#define MPHY_TX_FSM_STATE_ARG1 0x00410000u /* attribute 0x41, lane0 selector */
#define HCS_ENTRY 0x10fu /* list ready bits3:0 = 15 (UIC ready is bit3 = 0x8),
                          * UPMCRS powerstatus bits10:8 = 1 */
#define HCS_ENTRY_NO_PWR 0x00fu /* same list ready bits, UPMCRS powerstatus 0 */
#define FW_BASE_LO 0x11110000u
#define FW_BASE_HI 2u
#define UCD_OFFSET 1024u
#define RSP_OFFSET 1536u
#define DMA_BASE UINT64_C(0x10000000)
#define ARENA_BYTES 8192u
/* Bounded polling: a frozen timer must still terminate well below this. */
#define READ_CEILING 300000u

static _Alignas(1024) unsigned char arena[ARENA_BYTES];

struct fixture {
    uint32_t reg[0x304 / 4];
    uint64_t ticks;
    unsigned writes, reads, dev_syncs, cpu_syncs;
    unsigned get_calls, exit_calls, enter_calls, nop_calls, enter_done;
    unsigned fsm, exit_fsm;
    bool manage, freeze_timer;
    bool suppress_get_completion, get_bad_result;
    bool exit_only_uccs, exit_only_uhxs, exit_bad_power, exit_bad_result;
    bool enter_no_completion, enter_bad_power, confirm_sees_awake;
    bool fail_exit_arg1;
    bool stopped_lists_not_ready;
    char log[24];
    unsigned log_len;
};

static void note(struct fixture *f, char c)
{
    assert(f->log_len + 1 < sizeof(f->log));
    f->log[f->log_len++] = c;
}
static uint32_t rd_le32(const unsigned char *p)
{ return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

static int rd32(void *ctx, uint32_t off, uint32_t *value)
{
    struct fixture *f = ctx;
    assert(off < sizeof(f->reg));
    ++f->reads;
    *value = f->reg[off / 4];
    return 0;
}
/* Real UIC registers: a command is only accepted once the host list is
 * stopped and the queues are drained, arguments are already latched, and the
 * command completes by raising fresh interrupt status bits. */
static void uic(struct fixture *f, uint32_t command)
{
    assert(f->reg[REG_DOORBELL / 4] == 0);
    assert(f->reg[REG_TASK_DB / 4] == 0);
    assert((f->reg[REG_RUN / 4] & 1u) == 0);
    /* A stopped list leaves only device present (bit0) and UIC ready (bit3);
     * bits2:1 are withdrawn, so a host that waits for them never proceeds. */
    if (f->stopped_lists_not_ready)
        assert((f->reg[REG_HCS / 4] & 0xfu) == 0x9u);
    switch (command) {
    case UIC_DME_GET:
        assert(f->reg[REG_UIC_ARG1 / 4] == MPHY_TX_FSM_STATE_ARG1);
        assert(f->reg[REG_UIC_ARG2 / 4] == 0 && f->reg[REG_UIC_ARG3 / 4] == 0);
        ++f->get_calls;
        note(f, 'G');
        /* Completion layout: ARG2 carries the result/error code (0 success,
         * 0x10 failure), ARG3 carries the returned TX FSM state. */
        f->reg[REG_UIC_ARG2 / 4] = f->get_bad_result ? 0x10u : 0u;
        f->reg[REG_UIC_ARG3 / 4] = (f->enter_done && f->confirm_sees_awake)
            ? TX_FSM_AWAKE : f->fsm;
        if (!f->suppress_get_completion) f->reg[REG_IS / 4] |= IS_UCCS;
        return;
    case UIC_DME_HIBERN8_EXIT:
        assert(f->reg[REG_UIC_ARG1 / 4] == 0);
        assert(f->reg[REG_UIC_ARG2 / 4] == 0 && f->reg[REG_UIC_ARG3 / 4] == 0);
        assert(f->fsm == TX_FSM_HIBERN8);
        ++f->exit_calls;
        note(f, 'X');
        f->fsm = f->exit_fsm;
        if (f->exit_only_uccs) f->reg[REG_IS / 4] |= IS_UCCS;
        else if (f->exit_only_uhxs) f->reg[REG_IS / 4] |= IS_UHXS;
        else f->reg[REG_IS / 4] |= IS_UCCS | IS_UHXS;
        f->reg[REG_HCS / 4] = (f->reg[REG_HCS / 4] & ~0x700u) |
                              ((f->exit_bad_power ? 2u : 1u) << 8);
        f->reg[REG_UIC_ARG2 / 4] = f->exit_bad_result ? 0x10u : 0;
        return;
    case UIC_DME_HIBERN8_ENTER:
        assert(f->reg[REG_UIC_ARG1 / 4] == 0);
        assert(f->reg[REG_UIC_ARG2 / 4] == 0 && f->reg[REG_UIC_ARG3 / 4] == 0);
        /* ENTER is only meaningful from a known awake state, which includes
         * SLEEP, STALL, LSBURST and HSBURST. */
        assert(f->fsm >= TX_FSM_SLEEP && f->fsm <= TX_FSM_HSBURST);
        ++f->enter_calls;
        f->enter_done = 1;
        note(f, 'E');
        if (f->enter_no_completion) return; /* stuck: nothing ever completes */
        f->fsm = TX_FSM_HIBERN8;
        f->reg[REG_IS / 4] |= IS_UCCS | IS_UHES;
        f->reg[REG_HCS / 4] = (f->reg[REG_HCS / 4] & ~0x700u) |
                              ((f->enter_bad_power ? 2u : 1u) << 8);
        f->reg[REG_UIC_ARG2 / 4] = 0;
        return;
    }
    assert(0 && "UIC command outside the contract");
}
static void complete_nop(struct fixture *f)
{
    unsigned char *ucd = arena + UCD_OFFSET, *rsp = arena + RSP_OFFSET;
    assert(rd_le32(arena + 16) == (uint32_t)(DMA_BASE + UCD_OFFSET));
    assert(rd_le32(arena + 20) == 0);
    assert(ucd[0] == 0 && ucd[2] == 0 && ucd[3] == 0); /* NOP, LUN0, tag0 */
    /* Hibernated link: the request never leaves, so the descriptor keeps its
     * pending state and the real transport times out. */
    if (f->fsm == TX_FSM_HIBERN8) return;
    memset(rsp, 0, 512);
    rsp[0] = (unsigned char)(ucd[0] + 0x20);
    rsp[2] = ucd[2];
    arena[8] = 0; /* OCS success */
    f->reg[REG_IS / 4] |= IS_UTCS;
    f->reg[REG_DOORBELL / 4] = 0;
}
static int wr32(void *ctx, uint32_t off, uint32_t value)
{
    struct fixture *f = ctx;
    ++f->writes;
    switch (off) {
    case REG_AHIT: case REG_IE: case REG_BASE_LO: case REG_BASE_HI:
    case REG_UIC_ARG2: case REG_UIC_ARG3:
        f->reg[off / 4] = value;
        return 0;
    case REG_RUN:
        f->reg[off / 4] = value;
        /* Starting or stopping the list is what drives the transfer and task
         * list ready bits; UIC ready and device present are unaffected. */
        if (f->stopped_lists_not_ready)
            f->reg[REG_HCS / 4] = (value & 1u)
                ? (f->reg[REG_HCS / 4] | 0x6u)
                : (f->reg[REG_HCS / 4] & ~0x6u);
        return 0;
    case REG_UIC_ARG1:
        /* One-shot transport fault: the HIBERN8_EXIT argument write fails
         * after the entry query, so the command is never triggered. GET uses
         * a non-zero attribute selector, so ARG1 zero identifies the exit. */
        if (f->fail_exit_arg1 && value == 0 && f->get_calls == 1) {
            f->fail_exit_arg1 = false;
            return 1;
        }
        f->reg[off / 4] = value;
        return 0;
    case REG_IS: /* W1C: clear exactly the bits written */
        f->reg[REG_IS / 4] &= ~value;
        return 0;
    case REG_DOORBELL:
        assert(value == 1);
        note(f, 'N');
        ++f->nop_calls;
        f->reg[REG_DOORBELL / 4] = 1; /* latched until the command completes */
        complete_nop(f);
        return 0;
    case REG_UIC_CMD:
        uic(f, value);
        return 0;
    }
    /* HCE, clock/SMMU/reset, DMESET and every other register are off limits:
     * a host handoff must never reset or reconfigure the controller. */
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
    return (struct kshim_ufs_ops){f, rd32, wr32, dev_sync, cpu_sync,
                                  now_ms, delay_us, f->manage};
}
static void init(struct fixture *f)
{
    memset(f, 0, sizeof(*f));
    memset(arena, 0, sizeof(arena));
    f->manage = true;
    f->fsm = TX_FSM_HIBERN8; /* the state the previous stage left behind */
    f->exit_fsm = TX_FSM_AWAKE; /* default exit outcome: STALL */
    f->reg[REG_CAP / 4] = 1u << 24; /* 64-bit addressing */
    f->reg[REG_HCE / 4] = 1;
    f->reg[REG_HCS / 4] = HCS_ENTRY;
    f->reg[REG_BASE_LO / 4] = FW_BASE_LO;
    f->reg[REG_BASE_HI / 4] = FW_BASE_HI;
    f->reg[REG_RUN / 4] = 1;
    f->reg[REG_IE / 4] = 0x400;
    f->reg[REG_AHIT / 4] = 0x123;
    f->reg[REG_DOORBELL / 4] = 0;
    f->reg[REG_TASK_DB / 4] = 0;
    f->reg[REG_IS / 4] = IS_UCCS; /* stale completion left by the firmware */
}
static void claim(struct fixture *f, struct kshim_ufs_host *h)
{
    struct kshim_ufs_ops o = ops_of(f);
    memset(h, 0, sizeof(*h));
    assert(kshim_ufs_claim(h, &o, arena, sizeof(arena), DMA_BASE) == 0);
}
static int log_at(const struct fixture *f, char c, unsigned from)
{
    for (unsigned i = from; i < f->log_len; ++i)
        if (f->log[i] == c) return (int)i;
    return -1;
}
static void assert_restored(const struct fixture *f)
{
    assert(f->reg[REG_BASE_LO / 4] == FW_BASE_LO);
    assert(f->reg[REG_BASE_HI / 4] == FW_BASE_HI);
    assert(f->reg[REG_RUN / 4] == 1);
    assert(f->reg[REG_IE / 4] == 0x400);
    assert(f->reg[REG_AHIT / 4] == 0x123);
}

/* A: the observed hardware failure, then the same entry state with link
 * management enabled. */
static void test_inherited_hibern8(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    /* Legacy reproducer: the flag is off, so the old semantics stand. */
    init(&f);
    f.manage = false;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == KSHIM_UFS_TIMEOUT);
    assert(kshim_ufs_release(&h) == KSHIM_UFS_BUSY);
    assert(f.get_calls == 0 && f.exit_calls == 0 && f.enter_calls == 0);
    assert(f.reg[REG_HCS / 4] == HCS_ENTRY);

    /* Managed claim on the same inherited HIBERN8 entry state. */
    init(&f);
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(f.exit_calls == 1 && f.enter_calls == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.exit_calls == 1 && f.enter_calls == 1);
    assert(f.fsm == TX_FSM_HIBERN8);
    int g0 = log_at(&f, 'G', 0);
    int x = log_at(&f, 'X', 0);
    int n = log_at(&f, 'N', 0);
    int e = log_at(&f, 'E', 0);
    assert(g0 >= 0 && x > g0 && n > x);
    assert(e > n && log_at(&f, 'G', (unsigned)(e + 1)) > e);
    assert_restored(&f);
    assert(h.owned == 0);
    assert(h.link.uncertain == 0 && h.link.restore_hibern8 == 0);
}

/* A2: every known normal awake TX FSM state is a usable entry state. The host
 * must not demand the single STALL value it first saw: SLEEP, LSBURST and
 * HSBURST all mean the link is up, so no power command is issued and the link
 * is handed back in the state it arrived in. */
static void test_known_awake_states(void)
{
    static const unsigned states[] = { TX_FSM_SLEEP, TX_FSM_LSBURST,
                                       TX_FSM_HSBURST };
    struct fixture f;
    struct kshim_ufs_host h;

    for (unsigned i = 0; i < sizeof(states) / sizeof(states[0]); ++i) {
        init(&f);
        f.fsm = states[i];
        claim(&f, &h);
        assert(kshim_ufs_nop(&h) == 0);
        assert(f.get_calls >= 1 && f.exit_calls == 0 && f.enter_calls == 0);
        assert(f.fsm == states[i]);
        assert(kshim_ufs_release(&h) == 0);
        assert(f.exit_calls == 0 && f.enter_calls == 0);
        assert(f.fsm == states[i]);
        assert_restored(&f);
        assert(h.owned == 0 && h.link.uncertain == 0 &&
               h.link.restore_hibern8 == 0);
    }
}

/* A3: an inherited HIBERN8 link may exit into any known awake state, not only
 * STALL. Here the exit reports 2/4/5; the NOP must still complete, and release
 * must re-enter HIBERN8 and confirm it. */
static void test_exit_to_awake_states(void)
{
    static const unsigned states[] = { TX_FSM_SLEEP, TX_FSM_LSBURST,
                                       TX_FSM_HSBURST };
    struct fixture f;
    struct kshim_ufs_host h;

    for (unsigned i = 0; i < sizeof(states) / sizeof(states[0]); ++i) {
        init(&f);
        f.exit_fsm = states[i];
        claim(&f, &h);
        assert(f.get_calls >= 2 && f.exit_calls == 1);
        assert(f.fsm == states[i]);
        assert(kshim_ufs_nop(&h) == 0);
        assert(kshim_ufs_release(&h) == 0);
        assert(f.enter_calls == 1 && f.fsm == TX_FSM_HIBERN8);
        int g0 = log_at(&f, 'G', 0);
        int x = log_at(&f, 'X', 0);
        int n = log_at(&f, 'N', 0);
        int e = log_at(&f, 'E', 0);
        assert(g0 >= 0 && x > g0 && n > x);
        assert(e > n && log_at(&f, 'G', (unsigned)(e + 1)) > e);
        assert_restored(&f);
        assert(h.owned == 0 && h.link.uncertain == 0 &&
               h.link.restore_hibern8 == 0);
    }
}

/* B: an awake entry link is used as-is. */
static void test_active_link(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.fsm = TX_FSM_AWAKE;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.get_calls >= 1 && f.exit_calls == 0 && f.enter_calls == 0);
    assert(f.fsm == TX_FSM_AWAKE);
    assert_restored(&f);
    assert(h.owned == 0 && h.link.uncertain == 0);
}

/* C: a stale UCCS bit must not be taken for the completion of the new query,
 * and a claim that gives up leaves the link state uncertain. */
static void test_stale_completion(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.suppress_get_completion = true;
    memset(&h, 0, sizeof(h));
    struct kshim_ufs_ops o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE)
           == KSHIM_UFS_TIMEOUT);
    assert(f.nop_calls == 0);
    assert(kshim_ufs_release(&h) != 0);
    assert(h.owned == 1);

    /* A stopped timer must not remove the bound: an iteration ceiling stands
     * in for it, so the read count stays under the ceiling. */
    init(&f);
    f.suppress_get_completion = true;
    f.freeze_timer = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE) != 0);
    assert(f.reads <= READ_CEILING);
    assert(f.nop_calls == 0);
}

/* D: the query itself reports a failure, but it did complete and changed
 * nothing, so the arena can still be handed back cleanly. */
static void test_bad_query_result(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.get_bad_result = true;
    memset(&h, 0, sizeof(h));
    struct kshim_ufs_ops o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE) != 0);
    assert(f.nop_calls == 0 && f.exit_calls == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert_restored(&f);
    assert(h.owned == 0 && h.link.uncertain == 0);
}

/* E: an exit completion needs both the command-complete and the
 * hibernation-exit status bits, freshly raised. */
static void test_partial_exit_completion(void)
{
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_ops o;

    init(&f);
    f.exit_only_uccs = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE)
           == KSHIM_UFS_TIMEOUT);
    assert(f.nop_calls == 0);
    assert(kshim_ufs_release(&h) != 0 && h.owned == 1);

    init(&f);
    f.exit_only_uhxs = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE)
           == KSHIM_UFS_TIMEOUT);
    assert(f.nop_calls == 0);
    assert(kshim_ufs_release(&h) != 0 && h.owned == 1);
}

/* F: a completed exit with a bad power status or a bad result code leaves an
 * uncertain link, which forbids handoff. */
static void test_bad_exit_result(void)
{
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_ops o;

    init(&f);
    f.exit_bad_power = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE) != 0);
    assert(f.nop_calls == 0);
    assert(kshim_ufs_release(&h) != 0 && h.owned == 1);
    assert(h.link.uncertain == 1);

    init(&f);
    f.exit_bad_result = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE) != 0);
    assert(f.nop_calls == 0);
    assert(kshim_ufs_release(&h) != 0 && h.owned == 1);
    assert(h.link.uncertain == 1);
}

/* G: an entry state outside the known normal set (DISABLED 0, the reserved 6
 * and 0xff) is rejected before any DMA is handed to the controller. */
static void test_unknown_entry_state(void)
{
    static const unsigned unknown[] = { TX_FSM_DISABLED, 6, 0xff };
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_ops o;

    for (unsigned i = 0; i < sizeof(unknown) / sizeof(unknown[0]); ++i) {
        init(&f);
        f.fsm = unknown[i];
        memset(&h, 0, sizeof(h));
        o = ops_of(&f);
        assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE) != 0);
        assert(f.exit_calls == 0 && f.nop_calls == 0 && f.dev_syncs == 0);
        assert(kshim_ufs_release(&h) == 0);
        assert_restored(&f);
        assert(h.owned == 0);
    }

    /* Control: the same fixture with the known awake state claims fine. */
    init(&f);
    f.fsm = TX_FSM_AWAKE;
    claim(&f, &h);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.fsm == TX_FSM_AWAKE);
}

/* H: a failed restore never reports the link as restored. */
static void test_failed_restore(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.enter_no_completion = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) != 0);
    assert(h.owned == 1 && h.link.restore_hibern8 == 1);
    assert(f.fsm == TX_FSM_AWAKE);

    init(&f);
    f.enter_bad_power = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) != 0);
    assert(h.owned == 1 && h.link.restore_hibern8 == 1);

    init(&f);
    f.confirm_sees_awake = true;
    claim(&f, &h);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) != 0);
    assert(h.owned == 1 && h.link.restore_hibern8 == 1);
}

/* I: UPMCRS reports the outcome of the previous power command, so a link
 * handed over with powerstatus 0 is still a valid hibernated entry state. The
 * exit is issued, and its own completion raises UPMCRS to 1. */
static void test_stale_upmcrs(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.reg[REG_HCS / 4] = HCS_ENTRY_NO_PWR;
    claim(&f, &h);
    assert(f.get_calls >= 1 && f.exit_calls == 1);
    assert(f.reg[REG_HCS / 4] == HCS_ENTRY);
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.enter_calls == 1 && f.fsm == TX_FSM_HIBERN8);
    assert_restored(&f);
    assert(h.owned == 0 && h.link.uncertain == 0 && h.link.restore_hibern8 == 0);
}

/* J: a failure before the exit trigger leaves the link untouched, so nothing
 * is owed: no restore entry, no transfer, and a clean firmware handoff. */
static void test_exit_argument_failure(void)
{
    struct fixture f;
    struct kshim_ufs_host h;
    struct kshim_ufs_ops o;

    init(&f);
    f.fail_exit_arg1 = true;
    memset(&h, 0, sizeof(h));
    o = ops_of(&f);
    assert(kshim_ufs_claim(&h, &o, arena, sizeof(arena), DMA_BASE)
           == KSHIM_STORAGE_IO);
    assert(f.get_calls == 1 && f.exit_calls == 0);
    assert(f.enter_calls == 0 && f.nop_calls == 0);
    assert(h.link.restore_hibern8 == 0 && h.link.uncertain == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.exit_calls == 0 && f.enter_calls == 0 && f.nop_calls == 0);
    assert(f.fsm == TX_FSM_HIBERN8);
    assert(h.link.restore_hibern8 == 0);
    assert_restored(&f);
    assert(h.owned == 0);
}

/* K: stopping our list withdraws the transfer and task list ready bits, so a
 * UIC readiness test that insists on the whole HCS bits3:0 never passes and
 * every managed claim fails busy. Only UIC ready (bit3) gates a UIC command,
 * and the entry query, the exit and the restore still run with our list
 * stopped and the queues drained. */
static void test_stopped_lists_uic_ready(void)
{
    struct fixture f;
    struct kshim_ufs_host h;

    init(&f);
    f.stopped_lists_not_ready = true;
    claim(&f, &h);
    assert(f.get_calls >= 1 && f.exit_calls == 1);
    assert((f.reg[REG_HCS / 4] & 0xfu) == 0xfu); /* list running after claim */
    assert(kshim_ufs_nop(&h) == 0);
    assert(kshim_ufs_release(&h) == 0);
    assert(f.enter_calls == 1 && f.fsm == TX_FSM_HIBERN8);
    int g0 = log_at(&f, 'G', 0);
    int x = log_at(&f, 'X', 0);
    int n = log_at(&f, 'N', 0);
    int e = log_at(&f, 'E', 0);
    assert(g0 >= 0 && x > g0 && n > x);
    assert(e > n && log_at(&f, 'G', (unsigned)(e + 1)) > e);
    assert(f.reg[REG_HCS / 4] == HCS_ENTRY); /* ready bits return with RUN */
    assert_restored(&f);
    assert(h.owned == 0 && h.link.uncertain == 0 && h.link.restore_hibern8 == 0);
}

int main(void)
{
    test_inherited_hibern8();
    test_known_awake_states();
    test_exit_to_awake_states();
    test_active_link();
    test_stale_completion();
    test_bad_query_result();
    test_partial_exit_completion();
    test_bad_exit_result();
    test_unknown_entry_state();
    test_failed_restore();
    test_stale_upmcrs();
    test_exit_argument_failure();
    test_stopped_lists_uic_ready();
    puts("storage_ufs_link_test: inherited HIBERN8 handoff contract: PASS");
    return 0;
}
