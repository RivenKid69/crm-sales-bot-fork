import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { UgdLicenseRepository } from './data/ugd-license.repository';
import { UgdLicenseService } from './domain/ugd-license.service';
import { UgdLicensesController } from './ugd-licenses.controller';

@Module({
  imports: [TypeOrmModule.forFeature([UgdLicenseRepository])],
  controllers: [UgdLicensesController],
  providers: [UgdLicenseService],
  exports: [UgdLicenseService],
})
export class UgdLicensesModule {}
