/* SPDX-License-Identifier: GPL-2.0-only */
int main(){
    root_regression();
    reset();endpoint_enabled=2;elden_pcie_native_start();CHECK(!queued&&!map_count);cases++;
    reset();endpoint_enabled=1;elden_pcie_native_start();EldenPcieEndpointStatus s={};
    CHECK(elden_pcie_endpoint_status(&s)==-11);execute();CHECK(!elden_pcie_endpoint_status(&s));
    CHECK(s.requested&&s.state==EldenEndpointIdentified&&s.stage==EldenEndpointComplete&&!s.error);
    CHECK(s.confirmed&&s.major==2&&s.minor==1&&s.command==2&&s.mapped&&s.remap_restored);
    CHECK(s.bar0==0x40400000&&s.bar0_bytes==0x200000&&s.bar2==0x40600000&&s.bar2_bytes==0x8000);
    CHECK(confirmed_calls==1&&ready_calls==1&&map_count==10&&terminal.error==0);cases++;
    elden_pcie_native_stop_begin();CHECK(!elden_pcie_endpoint_status(&s)&&!s.confirmed);
    provided_epoch=0;CHECK(!saved_quiesce(provider,7,now(nullptr)+9000000));
    CHECK(!elden_pcie_endpoint_status(&s)&&s.stopped&&!s.confirmed);cases++;
    reset();endpoint_enabled=1;map_fail=9;elden_pcie_native_start();execute();
    CHECK(!elden_pcie_endpoint_status(&s)&&s.error==-12&&!s.mapped&&!s.confirmed&&!confirmed_calls);cases++;
    for(unsigned fault=1;fault<=2;fault++){
        reset();endpoint_enabled=1;pcie_ep_fault(fault);elden_pcie_native_start();execute();
        CHECK(!elden_pcie_endpoint_status(&s)&&s.error&&!s.confirmed&&!confirmed_calls);
        CHECK(!terminal.error&&s.state==EldenEndpointHeld);cases++;
    }
    reset();endpoint_enabled=1;pcie_ep_stop(elden_pcie_native_stop_begin);elden_pcie_native_start();execute();
    CHECK(!elden_pcie_endpoint_status(&s)&&s.error==-11&&!s.confirmed&&!confirmed_calls);cases++;
    reset();endpoint_enabled=1;confirm_error=-5;elden_pcie_native_start();execute();
    CHECK(!elden_pcie_endpoint_status(&s)&&s.error==-5&&!s.confirmed&&confirmed_calls==1&&!ready_calls);cases++;
    reset();endpoint_enabled=1;ready_error=-5;elden_pcie_native_start();execute();
    CHECK(!elden_pcie_endpoint_status(&s)&&s.error==-5&&!s.confirmed&&confirmed_calls==1&&ready_calls==1);cases++;
    reset();endpoint_enabled=1;confirm_stops=true;elden_pcie_native_start();execute();
    CHECK(!elden_pcie_endpoint_status(&s)&&s.error==-11&&!s.confirmed);cases++;
    delete active;active=nullptr;pcie_test_destroy(hw);hw=nullptr;
    printf("%u native root+endpoint scenarios / %u checks passed\n",cases,assertions);return 0;
}
