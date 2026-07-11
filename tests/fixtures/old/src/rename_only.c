#include "rename_only.h"

void Sub_step(void)
{
  real_T rtb_Sum1;
  real_T rtb_Gain2;

  rtb_Sum1 = rtU.In1 + rtU.In2;
  rtb_Gain2 = rtb_Sum1 * 3.5;
  if (rtb_Sum1 > 0.0) {
    rtY.Out1 = rtb_Gain2;
  } else {
    rtY.Out1 = rtb_Sum1;
  }
}
