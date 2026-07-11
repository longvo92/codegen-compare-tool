/* Generated on : Tue Feb 17 08:45:01 2026 */
#include "real_change.h"

void Calc_step(void)
{
  /* saturation limit */
  if (rtU.In1 > 10) {
    rtY.Out1 = 10;
  } else {
    rtY.Out1 = rtU.In1;
  }
}
