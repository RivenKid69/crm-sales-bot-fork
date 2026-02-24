import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { UserDao } from '../../../../common/dao/user.dao';

@Injectable()
export class FindUserByIdUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  handle(userId: number): Promise<UserDao | undefined> {
    return this.usersRepository.findUserById(userId);
  }
}
