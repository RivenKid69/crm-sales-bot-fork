import { Body, Controller, Get, Ip, Param, Response, UseGuards, UseInterceptors } from '@nestjs/common';
import { Provider } from '../../../common/decorators/provider.decorator';
import { IpFilterGuard } from '../../../common/guards/ip-filter.guard';
import { BillingsService } from '../domain/billings.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiExcludeController } from '@nestjs/swagger';

@Controller('billing')
@ApiExcludeController()
@UseInterceptors(TransformInterceptor)
export class BillingsController {
  constructor(private readonly billingService: BillingsService) {}

  @Get('qiwi')
  @Provider('qiwi')
  @UseGuards(IpFilterGuard)
  async qiwiBilling(@Body() reqBody, @Ip() ip: string, @Response() response) {
    return await this.billingService.qiwiBilling(reqBody, ip, response);
  }

  @Get(' kaspi')
  async kaspiBilling(@Body() reqBody, @Ip() ip: string, @Response() response) {
    return await this.billingService.kaspiBilling(reqBody, ip, response);
  }

  @Get('kassa24')
  @Provider('kassa24')
  @UseGuards(IpFilterGuard)
  async kassa24Billing(@Body() reqBody, @Ip() ip: string, @Response() response) {
    return await this.billingService.kassaBilling(reqBody, ip, response);
  }

  @Get('cyberplat')
  @Provider('cyberplat')
  @UseGuards(IpFilterGuard)
  async cyberplatBilling(@Body() reqBody, @Ip() ip: string, @Response() response) {
    return await this.billingService.cyberplatBilling(reqBody, ip, response);
  }

  @Get('wooppay/:invoiceId')
  async wooppayBilling(@Body() reqBody, @Ip() ip: string, @Param('invoiceId') invoiceId: string) {
    return await this.billingService.wooppayBilling(reqBody, ip, invoiceId);
  }
}
