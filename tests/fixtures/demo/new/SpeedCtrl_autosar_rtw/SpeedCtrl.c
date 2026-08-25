/*
 * File: SpeedCtrl.c
 *
 * Code generated for Simulink model 'SpeedCtrl'.
 *
 * Model version                  : 2.32
 * Simulink Coder version         : 9.9 (R2023a)
 * C/C++ source code generated on : Thu Aug 14 17:26:44 2026
 *
 * Target selection: autosar.tlc
 */

#include "SpeedCtrl.h"
#include "rtwtypes.h"

ExtU_SpeedCtrl_T rtU;
ExtY_SpeedCtrl_T rtY;

/* Blend three independent driver inputs into one speed request. */
void SpeedCtrl_step(void)
{
  real_T gainTorque;
  real_T gainSpeed;
  real_T gainPedal;

  gainPedal = rtU.Pedal * 2.00;
  gainSpeed = rtU.Speed * 0.90;
  gainTorque = rtU.Torque * 1.10;

  rtY.SpeedRequest = gainTorque + gainSpeed + gainPedal;
}

/* [EOF] */
