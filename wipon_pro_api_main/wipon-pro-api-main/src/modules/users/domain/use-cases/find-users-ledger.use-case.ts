import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { LedgerDao } from '../../../../common/dao/ledger.dao';

@Injectable()
export class FindUsersLedgerUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  async handle(userId): Promise<LedgerDao | null> {
    const user = await this.usersRepository.findOne({
      where: { id: userId },
      relations: ['ledger', 'ledger.accounts'],
    });
    if (!user) return null;
    return user.ledger;
  }
}
