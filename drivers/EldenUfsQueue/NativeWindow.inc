  // The pool protects snapshot ownership, not the duration of the I/O.
  static constexpr unsigned kBounces=4;
  uint8_t *bounces[kBounces]={};uint32_t bounceFree=0;
  IOLock *windowLock=nullptr;bool online=false;
  uint8_t *takeBounce(){
    if(panic_active()||!queueReady())return nullptr;
    IOLockLock(windowLock);uint64_t deadline;
    clock_interval_to_deadline(1000,kMillisecondScale,&deadline);
    while(!bounceFree&&queueReady()){
      uint64_t now=mach_absolute_time();
      if(now>=deadline||!preemption_enabled()||!ml_get_interrupts_enabled())break;
      uint64_t left=0;absolutetime_to_nanoseconds(deadline-now,&left);
      uint32_t us=left/1000<1000?static_cast<uint32_t>(left/1000):1000;if(!us)break;
      if(assert_wait_timeout((event_t)&bounceFree,THREAD_UNINT,us,NSEC_PER_USEC)!=THREAD_WAITING)break;
      if(!queueReady()){clear_wait(current_thread(),THREAD_AWAKENED);break;}
      IOLockUnlock(windowLock);thread_block(THREAD_CONTINUE_NULL);IOLockLock(windowLock);
    }
    uint8_t *result=nullptr;
    if(bounceFree&&queueReady()){
      unsigned index=static_cast<unsigned>(__builtin_ctz(bounceFree));bounceFree&=~(1u<<index);result=bounces[index];
    }
    IOLockUnlock(windowLock);return result;
  }
  void giveBounce(uint8_t *buffer){
    IOLockLock(windowLock);
    if(!queueFailed())for(unsigned i=0;i<kBounces;i++)if(bounces[i]==buffer)bounceFree|=1u<<i;
    IOLockUnlock(windowLock);thread_wakeup((event_t)&bounceFree);
  }
