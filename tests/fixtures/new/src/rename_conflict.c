#include "rename_conflict.h"

void Conf_step(void)
{
  real_T rtb_B;

  rtb_B = rtU.In1 * 2.0;
  rtY.Out1 = rtb_B + 1.0;
  rtY.Out2 = rtb_C + 2.0;
}
