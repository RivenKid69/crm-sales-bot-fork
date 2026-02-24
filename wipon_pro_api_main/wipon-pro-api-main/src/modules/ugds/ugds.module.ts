import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UgdsRepository } from './data/ugds.repository';
import { UgdsService } from './domain/ugds.service';
import { UgdsController } from './presenter/ugds.controller';
import { FindUgdByDgdIdUseCase } from './domain/use-cases/find-ugd-by-dgd-id.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([UgdsRepository])],
  providers: [UgdsService, FindUgdByDgdIdUseCase],
  controllers: [UgdsController],
  exports: [FindUgdByDgdIdUseCase],
})
export class UgdsModule {}
