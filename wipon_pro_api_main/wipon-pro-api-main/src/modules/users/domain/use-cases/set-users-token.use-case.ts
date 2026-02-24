import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UsersRepository } from '../../data/users.repository';
import { UpdateResult } from 'typeorm';

@Injectable()
export class SetUsersTokenUseCase {
  constructor(@InjectRepository(UsersRepository) private readonly usersRepository: UsersRepository) {}

  handle(userId: number, apiToken: string): Promise<UpdateResult> {
    return this.usersRepository.setUsersToken(userId, apiToken);
  }
}
