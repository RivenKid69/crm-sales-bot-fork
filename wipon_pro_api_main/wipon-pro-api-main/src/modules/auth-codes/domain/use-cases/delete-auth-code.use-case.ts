import { InjectRepository } from '@nestjs/typeorm';
import { AuthCodesRepository } from '../../data/auth-codes.repository';
import { DeleteResult } from 'typeorm';

export class DeleteAuthCodeUseCase {
  constructor(@InjectRepository(AuthCodesRepository) private readonly authCodesRepository: AuthCodesRepository) {}

  handle(authCodeId: number): Promise<DeleteResult> {
    return this.authCodesRepository.delete(authCodeId);
  }
}
