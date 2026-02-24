import { Module } from '@nestjs/common';
import { UsersService } from './domain/users.service';
import { FindUserByPhoneUseCase } from './domain/use-cases/find-user-by-phone.use-case';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UsersRepository } from './data/users.repository';
import { CreateUserByPhoneUseCase } from './domain/use-cases/create-user-by-phone-use-case';
import { SetUsersTokenUseCase } from './domain/use-cases/set-users-token.use-case';
import { FindUserByTokenUseCase } from './domain/use-cases/find-user-by-token.use-case';
import { UsersController } from './presenter/users.controller';
import { FindUsersLedgerUseCase } from './domain/use-cases/find-users-ledger.use-case';
import { FindUserByIdUseCase } from './domain/use-cases/find-user-by-id.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([UsersRepository])],
  providers: [
    UsersService,
    FindUserByPhoneUseCase,
    CreateUserByPhoneUseCase,
    SetUsersTokenUseCase,
    FindUserByTokenUseCase,
    FindUsersLedgerUseCase,
    FindUserByIdUseCase,
  ],
  exports: [
    FindUserByPhoneUseCase,
    CreateUserByPhoneUseCase,
    SetUsersTokenUseCase,
    FindUserByTokenUseCase,
    FindUsersLedgerUseCase,
    FindUserByIdUseCase,
    UsersService,
  ],
  controllers: [UsersController],
})
export class UsersModule {}
