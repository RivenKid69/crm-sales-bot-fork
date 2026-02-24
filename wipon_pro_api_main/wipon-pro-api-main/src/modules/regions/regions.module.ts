import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { RegionsRepository } from './data/regions.repository';
import { FindRegionByNameUseCase } from './domain/use-cases/find-region-by-name.use-case';
import { FindRegionByIdUseCase } from './domain/use-cases/find-region-by-id.use-case';
import { RegionsService } from './domain/regions.service';
import { RegionsController } from './presenter/regions.controller';

@Module({
  imports: [TypeOrmModule.forFeature([RegionsRepository])],
  providers: [RegionsService, FindRegionByNameUseCase, FindRegionByIdUseCase],
  exports: [FindRegionByNameUseCase, FindRegionByIdUseCase],
  controllers: [RegionsController],
})
export class RegionsModule {}
