import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { AuthCodesRepository } from '../../data/auth-codes.repository';
import { AuthCodeDao } from '../../../../common/dao/auth-code.dao';

@Injectable()
export class FindNewestUsersAuthCodeUseCase {
  constructor(@InjectRepository(AuthCodesRepository) private readonly authCodesRepository: AuthCodesRepository) {}

  handle(userId: number): Promise<AuthCodeDao | null> {
    return this.authCodesRepository.findNewestUsersAuthCode(userId);
  }
}
