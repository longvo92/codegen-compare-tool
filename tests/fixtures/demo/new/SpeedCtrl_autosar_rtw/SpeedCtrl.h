/*
 * File: SpeedCtrl.h
 * Code generated for Simulink model 'SpeedCtrl'.
 */

#ifndef RTW_HEADER_SpeedCtrl_h_
#define RTW_HEADER_SpeedCtrl_h_

#include "rtwtypes.h"

typedef struct {
  real_T Torque;
  real_T Speed;
  real_T Pedal;
} ExtU_SpeedCtrl_T;

typedef struct {
  real_T SpeedRequest;
} ExtY_SpeedCtrl_T;

extern void SpeedCtrl_step(void);

#endif
