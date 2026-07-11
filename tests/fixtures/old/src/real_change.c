/* Generated on : Mon Jan 05 10:12:33 2026 */
#include "real_change.h"

void Calc_step(void)
{
  /* saturation limit */
  if (rtU.In1 > 5) {
    rtY.Out1 = 5;
  } else {
    rtY.Out1 = rtU.In1;
  }
}
