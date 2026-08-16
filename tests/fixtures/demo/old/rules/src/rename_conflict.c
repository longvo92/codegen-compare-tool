#include "rename_conflict.h"

void Conf_step(void)
{
  real_T rtb_A;

  rtb_A = rtU.In1 * 2.0;
  rtY.Out1 = rtb_A + 1.0;
  rtY.Out2 = rtb_A + 2.0;
}
