import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { UserDao } from '../../../../common/dao/user.dao';

@Injectable()
export class FindUserByPhoneUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  async handle(phoneNumber: string): Promise<UserDao | undefined> {
    return await this.usersRepository.findUserByPhoneNumber(phoneNumber);
  }
}
