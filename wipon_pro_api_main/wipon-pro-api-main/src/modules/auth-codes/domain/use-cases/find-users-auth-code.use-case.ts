import { Injectable } from '@nestjs/common';
import { AuthCodesRepository } from '../../data/auth-codes.repository';
import { InjectRepository } from '@nestjs/typeorm';

@Injectable()
export class FindUsersAuthCodeUseCase {
  constructor(
    @InjectRepository(AuthCodesRepository)
    private readonly authCodesRepository: AuthCodesRepository,
  ) {}
  handle(userId: number, authCode: string) {
    return this.authCodesRepository.findUsersAuthCode(userId, authCode);
  }
}
