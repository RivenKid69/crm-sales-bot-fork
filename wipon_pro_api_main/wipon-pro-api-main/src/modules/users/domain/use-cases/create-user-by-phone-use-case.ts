import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { UserDao } from '../../../../common/dao/user.dao';

export class CreateUserByPhoneUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  handle(phoneNumber: string): Promise<UserDao> {
    return this.usersRepository.createUserByPhoneNumber(phoneNumber);
  }
}
