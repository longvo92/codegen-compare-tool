/*
 * File: PedalMap.h
 * Code generated for Simulink model 'PedalMap'.
 * Model version                  : 4.07
 */

#ifndef RTW_HEADER_PedalMap_h_
#define RTW_HEADER_PedalMap_h_

#include "rtwtypes.h"

typedef struct {
  real_T Raw;
} ExtU_PedalMap_T;

typedef struct {
  real_T Scaled;
} ExtY_PedalMap_T;

extern void PedalMap_step(void);

#endif
