import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { DgdsRepostitory } from './data/dgds.repostitory';
import { FindDgdByNameUseCase } from './domain/use-cases/find-dgd-by-name.use-case';
import { DgdsService } from './domain/dgds.service';
import { DgdsController } from './presenter/dgds.controller';
import { FindDgdByIdUseCase } from './domain/use-cases/find-dgd-by-id.use-case';

@Module({
  imports: [TypeOrmModule.forFeature([DgdsRepostitory])],
  providers: [FindDgdByNameUseCase, DgdsService, FindDgdByIdUseCase],
  controllers: [DgdsController],
  exports: [FindDgdByNameUseCase, FindDgdByIdUseCase],
})
export class DgdsModule {}
