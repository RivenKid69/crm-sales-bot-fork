import { Controller, Post } from '@nestjs/common';
import { UgdLicenseService } from './domain/ugd-license.service';

@Controller('ugd-licenses')
export class UgdLicensesController {
  constructor(private readonly ugdLicenseService: UgdLicenseService) {}

  @Post('test')
  testController() {
    return this.ugdLicenseService.testService();
  }
}
