// SPDX-License-Identifier: BSD-2-Clause-Patent
// Copyright (c) 2026 Leo Zhang.
// User intent shared by the Apple80211 request threads and the radio's one
// worker. A stop survives a quick off/on or disconnect/join until the worker
// finishes the old station's teardown. Only the worker acknowledges stops.
#pragma once
#include <stdint.h>

namespace pianowifi {
struct WifiUserControl;
// SET19 and SET20 carry no user-origin bit. Keep boot safety until a root-
// controlled arm explicitly enables physical OFF. Neither startup ON nor
// automatic joins can establish that the user requested a power change.
struct WifiBootPower {
  uint32_t armed = 0;
  bool enabled = true; // configured once, before publishing the driver
  void arm() { __atomic_store_n(&armed, 1u, __ATOMIC_RELEASE); }
  bool isArmed() const { return __atomic_load_n(&armed, __ATOMIC_ACQUIRE) != 0; }
  bool suppressOff() const { return enabled && !isArmed(); }
  bool setPower(WifiUserControl &owner, bool on) const;
};

struct WifiUserControl {
  enum : uint32_t { kPower = 1, kJoin = 2, kCycle = 4, kSerial = 8 };
  uint32_t word = kPower | kJoin;
  uint32_t applied = 0;

  uint32_t read() const { return __atomic_load_n(&word, __ATOMIC_ACQUIRE); }
  static bool power(uint32_t w) { return (w & kPower) != 0; }
  static uint32_t serial(uint32_t w) { return w >> 3; }
  bool pending(uint32_t w) const { return serial(w) != __atomic_load_n(&applied, __ATOMIC_ACQUIRE); }
  bool allowed(uint32_t w) const { return (w & (kPower | kJoin | kCycle)) == (kPower | kJoin) && !pending(w); }
  bool radioStop() const { const uint32_t w = read(); return !power(w) || (w & kCycle); }

  uint32_t setPower(bool on) {
    uint32_t old = read(), next;
    do {
      if (power(old) == on) return old;
      next = on ? (old | kPower | kJoin) : ((old + kSerial) & ~(kPower | kJoin)) | kCycle;
    } while (!__atomic_compare_exchange_n(&word, &old, next, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return next;
  }
  uint32_t disconnect() {
    uint32_t old = read(), next;
    do {
      if (!(old & kJoin)) return old;
      next = (old + kSerial) & ~kJoin;
    } while (!__atomic_compare_exchange_n(&word, &old, next, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return next;
  }
  bool join() {
    uint32_t old = read();
    do {
      if (!power(old)) return false;
    } while (!__atomic_compare_exchange_n(&word, &old, old | kJoin, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
    return true;
  }
  void stopped(uint32_t w) { __atomic_store_n(&applied, serial(w), __ATOMIC_RELEASE); }
  // Called after WLAN_EN is low and DMA is disabled. A concurrent new off
  // remains pending if it arrived after this snapshot.
  void radioOff(uint32_t w) {
    uint32_t old = w;
    (void)__atomic_compare_exchange_n(&word, &old, w & ~kCycle, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
    stopped(w);
  }
};
inline bool WifiBootPower::setPower(WifiUserControl &owner, bool on) const
{
  if (!on && suppressOff()) return false;
  owner.setPower(on);
  return true;
}
}
