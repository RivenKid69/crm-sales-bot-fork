import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { UserDao } from '../../../../common/dao/user.dao';

@Injectable()
export class FindUserByTokenUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  async handle(apiToken: string): Promise<UserDao | null> {
    const user = await this.usersRepository.findOne({ where: { api_token: apiToken }, relations: ['ledger'] });
    if (!user) return null;
    return user;
  }
}
