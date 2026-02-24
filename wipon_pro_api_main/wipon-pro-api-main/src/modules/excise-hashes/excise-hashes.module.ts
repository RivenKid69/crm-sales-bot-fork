import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { ExciseHashesRepository } from './data/excise-hashes.repository';
import { FindOrCreateExciseHashUseCase } from './domain/use-cases/find-or-create-excise-hash.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([ExciseHashesRepository])],
  providers: [FindOrCreateExciseHashUseCase],
  exports: [FindOrCreateExciseHashUseCase],
})
export class ExciseHashesModule {}
