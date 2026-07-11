#include "rename_only.h"

void Sub_step(void)
{
  real_T rtb_Sum_k2j;
  real_T rtb_Gain_p0f;

  rtb_Sum_k2j = rtU.In1 + rtU.In2;
  rtb_Gain_p0f = rtb_Sum_k2j * 3.5;
  if (rtb_Sum_k2j > 0.0) {
    rtY.Out1 = rtb_Gain_p0f;
  } else {
    rtY.Out1 = rtb_Sum_k2j;
  }
}
