import { Module } from '@nestjs/common';
import { FindUsersAuthCodeUseCase } from './domain/use-cases/find-users-auth-code.use-case';
import { AuthCodesRepository } from './data/auth-codes.repository';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DeleteAuthCodeUseCase } from './domain/use-cases/delete-auth-code.use-case';
import { FindNewestUsersAuthCodeUseCase } from './domain/use-cases/find-newest-users-auth-code.use-case';
import { DeleteUsersAllAuthCodesUseCase } from './domain/use-cases/delete-users-all-auth-codes.use-case';
import { CreateUsersAuthCodeUseCase } from './domain/use-cases/create-users-auth-code.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([AuthCodesRepository])],
  providers: [
    FindUsersAuthCodeUseCase,
    DeleteAuthCodeUseCase,
    FindNewestUsersAuthCodeUseCase,
    DeleteUsersAllAuthCodesUseCase,
    CreateUsersAuthCodeUseCase,
  ],
  exports: [
    FindUsersAuthCodeUseCase,
    DeleteAuthCodeUseCase,
    FindNewestUsersAuthCodeUseCase,
    DeleteUsersAllAuthCodesUseCase,
    CreateUsersAuthCodeUseCase,
  ],
})
export class AuthCodesModule {}
