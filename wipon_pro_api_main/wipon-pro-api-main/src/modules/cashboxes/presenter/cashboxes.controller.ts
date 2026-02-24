import { Body, Controller, Post, UseGuards, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { CashboxesService } from '../domain/cashboxes.service';
import { PushAuthcodeDto } from '../dto/push-authcode.dto';
import { Provider } from '../../../common/decorators/provider.decorator';
import { IpFilterGuard } from '../../../common/guards/ip-filter.guard';
import { PushMessageDto } from '../dto/push-message.dto';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiExcludeController } from '@nestjs/swagger';

@ApiExcludeController()
@Controller('cashbox')
@UseInterceptors(TransformInterceptor)
export class CashboxesController {
  constructor(private readonly cashboxesService: CashboxesService) {}

  @Post('authcode-push')
  @Provider('prokassa')
  @UseGuards(IpFilterGuard)
  @UsePipes(ValidationPipe)
  async pushAuthCode(@Body() pushAuthCodeDto: PushAuthcodeDto) {
    return await this.cashboxesService.pushAuthCode(pushAuthCodeDto);
  }

  @Post('message-push')
  @Provider('prokassa')
  @UseGuards(IpFilterGuard)
  @UsePipes(ValidationPipe)
  async pushMessage(@Body() pushMsgDto: PushMessageDto) {
    return await this.cashboxesService.pushMessage(pushMsgDto);
  }
}
