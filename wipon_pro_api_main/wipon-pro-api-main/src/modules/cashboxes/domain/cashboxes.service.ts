import { Injectable, NotFoundException } from '@nestjs/common';
import { PushAuthcodeDto } from '../dto/push-authcode.dto';
import { FindUserByPhoneUseCase } from '../../users/domain/use-cases/find-user-by-phone.use-case';
import { PushService } from '../../../common/services/push/push.service';
import { PushMessageDto } from '../dto/push-message.dto';

@Injectable()
export class CashboxesService {
  constructor(private readonly findUserByPhone: FindUserByPhoneUseCase, private readonly pushService: PushService) {}

  async pushAuthCode(pushAuthCodeDto: PushAuthcodeDto) {
    const user = await this.findUserByPhone.handle(pushAuthCodeDto.phone_number);
    const status = await this.pushService.send(user, `Ключ для активации Pro Касса ${pushAuthCodeDto.auth_code}`);
    return {
      status: status ? 'success' : 'fail',
    };
  }

  async pushMessage(pushMsgDto: PushMessageDto) {
    const user = await this.findUserByPhone.handle(pushMsgDto.phone_number);
    if (!user) throw new NotFoundException({ message: 'Пользователь с таким номером телефона не найден' });
    const status = await this.pushService.send(user, pushMsgDto.message);
    return {
      status: status ? 'success' : 'fail',
    };
  }
}
