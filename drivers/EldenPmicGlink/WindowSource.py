"""Leave automatic window enforcement to OEM firmware; release our manual inhibit."""
from VerificationSource import policy as verified_policy, replace


def policy():
    text = verified_policy().decode('utf-8')
    start = text.index('static uint32_t permitted_enable(')
    end = text.index('void elden_charge_policy_observe(', start)
    text = text[:start] + text[end:]
    text = replace(text, '''        s->target_enable=permitted_enable(s);
        if(s->target_enable==enabled)done(s);else s->phase=EldenPolicySetEnable;''', '''        /* SET28=0 also latches the OEM manual bypass flag. A window's
         * temporary hold must never be implemented with that sticky command.
         * The verified SET29/GET29 delegates thresholds and hysteresis to OEM.
         * Leaving our explicit bypass must clear its flag even above the
         * window ceiling, where the effective charging permission can stay0. */
        if(s->applied_mode==EldenChargeBypass){
            s->target_enable=1;s->phase=EldenPolicySetEnable;
        }else{
            s->firmware_held=enabled==0;done(s);
        }''')
    return text.encode('utf-8')
