/* SPDX-License-Identifier: MIT
 * Read-only evdev witness: no EVIOCGRAB, injection, pairing or sysfs writes.
 * Reopens devices after panel/input re-registration and flushes every line.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <glob.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
enum { MAX_INPUTS=4 };
static volatile sig_atomic_t done;
static void stop(int sig){(void)sig;done=1;}
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
struct source {int fd; char path[128],name[128]; ino_t inode; dev_t dev; unsigned long count;};
static int wanted(const char *name){return !strcmp(name,"NVTCapacitivePen")||!strcmp(name,"Lenovo Tab Pen Plus Mouse")||!strcmp(name,"Lenovo Tab Pen Plus Consumer Control");}
int main(int argc,char **argv){
 if(argc!=2){fprintf(stderr,"usage: read_y700_pen SECONDS(1..600)\n");return 2;}
 char *end;long seconds=strtol(argv[1],&end,10);if(*end||seconds<1||seconds>600)return 2;
 setvbuf(stdout,NULL,_IOLBF,0);signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGHUP,stop);
 struct source sources[MAX_INPUTS]={0};for(int i=0;i<MAX_INPUTS;i++)sources[i].fd=-1;
 double start=now(),scan=0,heartbeat=0;unsigned total=0,opened=0;puts("READ_ONLY no-grab no-write");
 while(!done&&now()-start<seconds){
  double t=now();
  if(t>=scan){
   scan=t+1;
   for(int i=0;i<MAX_INPUTS;i++)if(sources[i].fd>=0){
    struct stat st;
    if(stat(sources[i].path,&st)||st.st_ino!=sources[i].inode||st.st_rdev!=sources[i].dev){printf("DETACHED %s\n",sources[i].path);close(sources[i].fd);sources[i].fd=-1;}
   }
   glob_t g={0};
   if(!glob("/dev/input/event*",0,NULL,&g))for(size_t j=0;j<g.gl_pathc;j++){
    int duplicate=0,slot=-1;for(int i=0;i<MAX_INPUTS;i++){if(sources[i].fd>=0&&!strcmp(sources[i].path,g.gl_pathv[j]))duplicate=1;if(sources[i].fd<0)slot=i;}
    if(duplicate||slot<0)continue;
    int fd=open(g.gl_pathv[j],O_RDONLY|O_NONBLOCK|O_CLOEXEC);if(fd<0)continue;
    char name[128]={0};struct stat st;
    if(ioctl(fd,EVIOCGNAME(sizeof(name)),name)<0||!wanted(name)||fstat(fd,&st)){close(fd);continue;}
    struct source *s=&sources[slot];s->fd=fd;s->inode=st.st_ino;s->dev=st.st_rdev;s->count=0;
    snprintf(s->path,sizeof(s->path),"%s",g.gl_pathv[j]);snprintf(s->name,sizeof(s->name),"%s",name);
    printf("OPEN %s name=%s instance=%u\n",s->path,name,++opened);
    unsigned long axes[(ABS_MAX+sizeof(long)*8)/(sizeof(long)*8)]={0};
    if(ioctl(fd,EVIOCGBIT(EV_ABS,sizeof(axes)),axes)>=0)for(unsigned a=0;a<=ABS_MAX;a++){
     if(!(axes[a/(sizeof(long)*8)]&(1UL<<(a%(sizeof(long)*8)))))continue;
     struct input_absinfo info;if(!ioctl(fd,EVIOCGABS(a),&info))printf("AXIS %s code=%u min=%d max=%d value=%d resolution=%d\n",s->path,a,info.minimum,info.maximum,info.value,info.resolution);
    }
   }
   globfree(&g);
  }
  struct pollfd p[MAX_INPUTS];for(int i=0;i<MAX_INPUTS;i++)p[i]=(struct pollfd){sources[i].fd,POLLIN,0};
  int n=poll(p,MAX_INPUTS,100);if(n<0){if(errno==EINTR)continue;perror("poll");done=1;break;}
  for(int i=0;i<MAX_INPUTS;i++)if(sources[i].fd>=0&&p[i].revents){
   struct source *s=&sources[i];
   if(p[i].revents&(POLLERR|POLLHUP|POLLNVAL)){printf("HUP %s events=%lu\n",s->path,s->count);close(s->fd);s->fd=-1;continue;}
   struct input_event ev[64];ssize_t bytes;
   while((bytes=read(s->fd,ev,sizeof(ev)))>0){
    if(bytes%(ssize_t)sizeof(ev[0])){puts("ERROR partial event");done=1;break;}
    for(size_t k=0;k<(size_t)bytes/sizeof(ev[0]);k++){
     printf("EV %s %ld.%06ld type=%u code=%u value=%d\n",s->path,(long)ev[k].time.tv_sec,(long)ev[k].time.tv_usec,ev[k].type,ev[k].code,ev[k].value);s->count++;total++;
    }
   }
   if(bytes<0&&errno!=EAGAIN&&errno!=EINTR){printf("READ_ERROR %s errno=%d\n",s->path,errno);close(s->fd);s->fd=-1;}
  }
  if(t>=heartbeat){heartbeat=t+5;printf("HEARTBEAT elapsed=%.1f events=%u\n",t-start,total);}
 }
 for(int i=0;i<MAX_INPUTS;i++)if(sources[i].fd>=0)close(sources[i].fd);
 printf("END elapsed=%.1f events=%u signal=%d\n",now()-start,total,(int)done);return 0;
}
