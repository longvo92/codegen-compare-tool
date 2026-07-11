/*
 * File: comment_only.c
 * Code generated for Simulink model 'Model'.
 * Model version                  : 1.42
 * Simulink Coder version         : 9.8 (R2023a) 19-Nov-2022
 * C/C++ source code generated on : Mon Jan 05 10:12:33 2026
 */
#include "comment_only.h"

/* Model step function */
void Model_step(void)
{
  /* Outport: '<Root>/Out1' */
  rtY.Out1 = rtU.In1 * 2.0;
}
