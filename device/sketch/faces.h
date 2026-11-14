// Pure 13x8 rasterizer. No delays, heap allocation or hardware dependencies.
#pragma once
#include <stdint.h>
#include <string.h>

namespace Faces {
const int W=13, H=8;
// Rows read left to right; low 13 bits are pixels, MSB is left.
const uint16_t SMILE[8]={0,0x0444,0x0444,0,0x0802,0x0404,0x03f8,0};
const uint16_t SUN[8]={0x0040,0x0444,0x01f0,0x02a8,0x12a9,0x01f0,0x0444,0x0040};
const uint16_t SNOW[8]={0x0444,0x0250,0x01f0,0x1fff,0x01f0,0x0250,0x0444,0};
const uint16_t CHECK[8]={0,0x0002,0x0004,0x0008,0x0810,0x0420,0x0240,0x0180};
const uint16_t EYE[8]={0x1000,0x0800,0x07f0,0x0a88,0x12a4,0x0448,0x03f4,0x0002};
const uint16_t LAYER[8]={0x01b0,0x0248,0x0424,0x0a2a,0x0220,0x0220,0x03e0,0};
const uint16_t LEFT[8]={0,0x0100,0x0200,0x07f0,0x0200,0x0100,0,0};
const uint16_t RIGHT[8]={0,0x0010,0x0008,0x07fc,0x0008,0x0010,0,0};
const uint16_t DOT[8]={0,0,0,0x00e0,0x00e0,0,0,0};
// 3x5 font: five rows of three bits; A-Z then 0-9.
const uint8_t FONT[36][5]={
 {2,5,7,5,5},{6,5,6,5,6},{3,4,4,4,3},{6,5,5,5,6},{7,4,6,4,7},{7,4,6,4,4},
 {3,4,5,5,3},{5,5,7,5,5},{7,2,2,2,7},{1,1,1,5,2},{5,5,6,5,5},{4,4,4,4,7},
 {5,7,7,5,5},{5,7,7,7,5},{2,5,5,5,2},{6,5,6,4,4},{2,5,5,3,1},{6,5,6,5,5},
 {3,4,2,1,6},{7,2,2,2,2},{5,5,5,5,7},{5,5,5,5,2},{5,5,7,7,5},{5,5,2,5,5},
 {5,5,2,2,2},{7,1,2,4,7},{7,5,5,5,7},{2,6,2,2,7},{6,1,2,4,7},{6,1,2,1,6},
 {5,5,7,1,1},{7,4,6,1,6},{3,4,7,5,7},{7,1,2,2,2},{7,5,7,5,7},{7,5,7,1,6}
};
inline void pixel(uint8_t *out,int x,int y) { if(x>=0 && x<W && y>=0 && y<H) out[y*W+x]=1; }
inline void rows(uint8_t *out,const uint16_t *r) {
 for(int y=0;y<H;y++) for(int x=0;x<W;x++) out[y*W+x]=(r[y]>>(W-1-x))&1;
}
inline void text(uint8_t *out,const char *s,uint32_t elapsed) {
 int n=0; while(s[n] && n<8) n++;
 int width=n*4-1;
 // Short words stay centered; long words scroll right-to-left with a blank gap.
 int origin=width<=W ? (W-width)/2 : W-int((elapsed/150)%(width+W+4));
 for(int i=0;i<n;i++) {
  int index=s[i]>='A' && s[i]<='Z' ? s[i]-'A' : s[i]>='0' && s[i]<='9' ? 26+s[i]-'0' : -1;
  if(index<0) continue;
  for(int y=0;y<5;y++) for(int x=0;x<3;x++) if(FONT[index][y]&(1<<(2-x))) pixel(out,origin+i*4+x,y+1);
 }
}
inline void render(uint8_t *out,const char *name,int pos,const char *s,uint32_t elapsed) {
 memset(out,0,W*H);
 if(!strcmp(name,"smile")) rows(out,SMILE);
 else if(!strcmp(name,"sun")) rows(out,SUN);
 else if(!strcmp(name,"snow")) rows(out,SNOW);
 else if(!strcmp(name,"check")) rows(out,CHECK);
 else if(!strcmp(name,"feedback")) rows(out,pos<0?LEFT:pos>0?RIGHT:DOT);
 else if(!strcmp(name,"text")) text(out,s,elapsed);
 else if(!strcmp(name,"eye_off")) { if(elapsed<3000) rows(out,EYE); else pixel(out,12,7); }
 else if(!strcmp(name,"suggest_layer_on") || !strcmp(name,"suggest_layer_off")) {
  if((elapsed/500)%2==0) {
   rows(out,LAYER);
   // Plus/minus at the right distinguishes adding from removing a layer.
   for(int x=10;x<13;x++) pixel(out,x,5);
   if(!strcmp(name,"suggest_layer_on")) { pixel(out,11,4); pixel(out,11,6); }
  }
 }
 // off or unknown -> blank.
}
}
