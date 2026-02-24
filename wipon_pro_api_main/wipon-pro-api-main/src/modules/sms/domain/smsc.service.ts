import { Injectable } from '@nestjs/common';
import { PostCallbackDto } from '../dto/post-callback.dto';
import { createCustomLogger } from '../../../common/logger/request-logger';
import appConfig from '../../../config/app.config';
import { DoomguyService } from '../../../common/services/doomguy/doomguy.service';

@Injectable()
export class SmscService {
  constructor(private readonly doomguyService: DoomguyService) {}

  async postCallback(postCbDto: PostCallbackDto) {
    const id = postCbDto.id;
    const phone = postCbDto.phone;
    const status = postCbDto.status;
    // const sha1 = postCbDto.sha1;

    const logger = createCustomLogger('info', 'smsc');
    const smsToken = appConfig.smsToken;

    const crypto = await import('crypto');
    const hashOfStr = crypto.createHash('sha1').update(`${id}:${phone}:${status}${smsToken}`).digest('base64');
    if (postCbDto.sha1 != hashOfStr) {
      logger.log('info', {
        msg: 'Callback called with an invalid hash',
        input: postCbDto,
      });
      return;
    }

    await this.doomguyService.sendSmsCallback(postCbDto);
    logger.log('info', { msg: 'Sms callback', data: postCbDto });
  }
}
