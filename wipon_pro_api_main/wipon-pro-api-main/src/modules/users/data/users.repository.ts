import { EntityRepository, Repository, UpdateResult } from 'typeorm';
import { UserDao } from '../../../common/dao/user.dao';

@EntityRepository(UserDao)
export class UsersRepository extends Repository<UserDao> {
  async findUserByPhoneNumber(phoneNumber: string): Promise<UserDao | undefined> {
    return await this.findOne({ where: { phone_number: phoneNumber }, relations: ['ledger'] });
  }

  async findUserById(userId): Promise<UserDao | undefined> {
    return await this.findOne({ where: { id: userId }, relations: ['ledger'] });
  }

  async createUserByPhoneNumber(phoneNumber: string): Promise<UserDao> {
    return await this.save({ phone_number: phoneNumber, created_at: new Date() });
  }

  async getUserByToken(token: string): Promise<UserDao | undefined> {
    return await this.findOne({ api_token: token });
  }

  async setUsersToken(userId: number, apiToken: string): Promise<UpdateResult> {
    return await this.update(userId, {
      api_token: apiToken,
    });
  }
}
