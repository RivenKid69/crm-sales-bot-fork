import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { AuthCodesRepository } from '../../data/auth-codes.repository';
import { addMinutesFromNow } from '../../../../common/helpers/datetime';
import authConfig from '../../../../config/auth.config';
import generateAuthCode from '../../../../common/helpers/generateAuthCode';
import { AuthCodeDao } from '../../../../common/dao/auth-code.dao';

@Injectable()
export class CreateUsersAuthCodeUseCase {
  constructor(@InjectRepository(AuthCodesRepository) private readonly authCodesRepository: AuthCodesRepository) {}

  async handle(userId: number): Promise<AuthCodeDao> {
    return await this.authCodesRepository.save({
      user_id: userId,
      code: generateAuthCode(),
      expires_at: addMinutesFromNow(authConfig.authCodes.lifetime),
      created_at: new Date(),
      updated_at: new Date(),
    });
  }
}
