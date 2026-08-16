/* Model step function */
#include "Ctrl.h"

void Ctrl_Step(void)
{
  Float32 u;
  (void) Rte_Read_In1_Speed(&u);
  (void) Rte_Write_Out1_Cmd(u * 3.0F);
  (void) Rte_Write_Out2_Diag(1U);
}
