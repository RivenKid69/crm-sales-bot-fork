import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { AuthCodesRepository } from '../../data/auth-codes.repository';
import { DeleteResult } from 'typeorm';

@Injectable()
export class DeleteUsersAllAuthCodesUseCase {
  constructor(@InjectRepository(AuthCodesRepository) private readonly authCodesRepository: AuthCodesRepository) {}

  async handle(userId: number): Promise<DeleteResult> {
    return await this.authCodesRepository.delete({ user_id: userId });
  }
}
