import { Injectable, UnprocessableEntityException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../data/users.repository';
import { UpdateUserDto } from '../dto/update-user.dto';
import { Not } from 'typeorm';
import { UserDao } from '../../../common/dao/user.dao';

@Injectable()
export class UsersService {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepo: UsersRepository) {}

  getUserWithStore(userId: number) {
    return this.usersRepo.findOne({ where: { id: userId }, relations: ['store'] });
  }

  async updateUser(updateUserDto: UpdateUserDto, user: UserDao) {
    if (updateUserDto.phone_number) {
      const isPhoneUniqueIgnoreCurrentUser = await this.usersRepo.count({
        where: { phone_number: updateUserDto.phone_number, id: Not(user.id) },
      });
      if (isPhoneUniqueIgnoreCurrentUser) {
        throw new UnprocessableEntityException({ phone_number: ['The phone number has already been taken'] });
      }
    }

    const data = new UserDao({ ...updateUserDto });
    await this.usersRepo.update(user.id, data);
    return {
      status: 'success',
    };
  }

  async updateUserData(user: UserDao) {
    await this.usersRepo.save(user);
    return {
      status: 'success',
    };
  }
}
