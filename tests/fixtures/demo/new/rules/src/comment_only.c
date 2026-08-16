/*
 * File: comment_only.c
 * Code generated for Simulink model 'Model'.
 * Model version                  : 1.43
 * Simulink Coder version         : 9.8 (R2023a) 19-Nov-2022
 * C/C++ source code generated on : Tue Feb 17 08:45:01 2026
 */
#include "comment_only.h"

/* Model step function (regenerated) */
void Model_step(void)
{
  /* Outport: '<Root>/Out1' */
  rtY.Out1 = rtU.In1 * 2.0;
}
