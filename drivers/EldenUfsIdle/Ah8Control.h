// SPDX-License-Identifier: BSD-2-Clause-Patent
#pragma once
#include <stdint.h>
// UFSHCI register facts + qcom UFS_AH8_CFG from the fixed TB322FC Linux source.
// Native caller holds the host/pool mutex. This class never waits for a busy
// queue, resets/cancels it, touches clocks outside the HC or changes a charger.
struct EldenAh8Control {
    enum Phase {Fresh,Changing,Enabled,Restoring,Restored,Held};
    Phase phase=Fresh;
    uint32_t oldCfg=0,oldIe=0,oldTimer=0,error=0;
    static constexpr uint32_t timer=0x5f4; // 500 *10us = stock5000us
    static constexpr uint32_t clockMask=0x3c,errorMask=0x60;
    template<class IO> int start(IO &io){
        if(phase==Enabled)return 0;
        if(phase!=Fresh||!io.idle())return -1;
        uint32_t cap=io.read(0),version=io.read(0xe4),tick=io.read(0xc0);
        if(!(cap&0x00800000)||version==UINT32_MAX||(version>>28)<3||!tick||tick==UINT32_MAX)return -2;
        if((io.read(0x30)&0x3f)!=0x0f||io.read(0x58)||io.read(0x78)||!(io.read(0x60)&1)||io.read(0x20)&0x718e4)return -3;
        oldCfg=io.read(0xfc);oldIe=io.read(0x24);oldTimer=io.read(0x18);
        if(oldIe!=1||oldTimer!=0)return -4;
        phase=Changing;
        io.write(0xfc,oldCfg|clockMask);
        if((io.read(0xfc)&clockMask)!=clockMask){phase=Held;error=5;return -5;}
        io.active(true);io.write(0x24,oldIe|errorMask);
        if(io.read(0x24)!=(oldIe|errorMask)){phase=Held;error=6;return -6;}
        io.write(0x18,timer);
        if(io.read(0x18)!=timer){phase=Held;error=7;return -7;}
        phase=Enabled;return 0;
    }
    template<class IO> int stop(IO &io){
        if(phase==Fresh||phase==Restored)return 0;
        if(!io.idle()||io.read(0x58)||io.read(0x78))return -1;
        phase=Restoring;
        // Disable autonomous transitions and their IRQs before manual UIC wake.
        io.write(0x18,oldTimer);
        if(io.read(0x18)!=oldTimer){phase=Held;error=8;return -8;}
        io.write(0x24,oldIe);
        if(io.read(0x24)!=oldIe){phase=Held;error=9;return -9;}
        io.active(false);
        if(io.read(0x20)&0x718e4||!io.wake()){phase=Held;error=10;return -10;}
        uint32_t current=io.read(0xfc);
        io.write(0xfc,(current&~clockMask)|(oldCfg&clockMask));
        if((io.read(0xfc)&clockMask)!=(oldCfg&clockMask)){phase=Held;error=11;return -11;}
        phase=Restored;return 0;
    }
};
