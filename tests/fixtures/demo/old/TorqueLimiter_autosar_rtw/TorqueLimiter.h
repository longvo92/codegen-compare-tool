/*
 * File: TorqueLimiter.h
 * Code generated for Simulink model 'TorqueLimiter'.
 */

#ifndef RTW_HEADER_TorqueLimiter_h_
#define RTW_HEADER_TorqueLimiter_h_

#include "rtwtypes.h"

typedef struct {
  real_T PedalPosition;
  real_T MotorSpeed;
} ExtU_TorqueLimiter_T;

typedef struct {
  real_T TorqueCmd;
} ExtY_TorqueLimiter_T;

extern void Rte_Runnable_TorqueLimiter_Step(void);

#endif
