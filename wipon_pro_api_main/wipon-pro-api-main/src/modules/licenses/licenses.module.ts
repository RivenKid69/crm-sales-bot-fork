import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { LicensesRepository } from './data/licenses.repository';
import { LicensesService } from './domain/licenses.service';
import { LicensesController } from './presenter/licenses.controller';
import { UsersModule } from '../users/users.module';

@Module({
  imports: [TypeOrmModule.forFeature([LicensesRepository]), UsersModule],
  providers: [LicensesService],
  controllers: [LicensesController],
})
export class LicensesModule {}
