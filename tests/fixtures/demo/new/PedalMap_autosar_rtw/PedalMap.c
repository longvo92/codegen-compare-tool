/*
 * File: PedalMap.c
 * Code generated for Simulink model 'PedalMap'.
 * Model version                  : 4.11
 */

#include "PedalMap.h"
#include "rtwtypes.h"

/* Scale the raw pedal reading into a normalised request. */
void PedalMap_step(void)
{
  rtY.Scaled = rtU.Raw * K_PedalGain + K_PedalOffset;
}

/* [EOF] */
