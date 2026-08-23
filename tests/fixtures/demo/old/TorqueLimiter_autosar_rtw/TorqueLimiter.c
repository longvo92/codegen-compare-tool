/*
 * File: TorqueLimiter.c
 *
 * Code generated for Simulink model 'TorqueLimiter'.
 *
 * Model version                  : 1.148
 * Simulink Coder version         : 9.9 (R2023a)
 * C/C++ source code generated on : Mon Aug 11 09:14:22 2026
 *
 * Target selection: autosar.tlc
 */

#include "TorqueLimiter.h"
#include "rtwtypes.h"

extern real_T TorqueLimiter_LookupTorque(real_T speed);

/* Model step function -- runs every 10 ms. */
void Rte_Runnable_TorqueLimiter_Step(void)
{
  real_T rtb_Request;
  real_T rtb_Ceiling;

  rtb_Request = rtU.PedalPosition * 300.0;
  rtb_Ceiling = TorqueLimiter_LookupTorque(rtU.MotorSpeed);

  /* Gain: apply the driveability scaling factor to the raw request */
  rtb_Request = rtb_Request * 1.25;

  if (rtb_Request > rtb_Ceiling) {
    rtb_Request = rtb_Ceiling;
  }

  rtY.TorqueCmd = rtb_Request;
}

/* [EOF] */
