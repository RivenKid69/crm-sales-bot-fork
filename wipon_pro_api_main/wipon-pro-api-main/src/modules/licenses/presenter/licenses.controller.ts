import { Body, Controller, Get, UseGuards, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { LicensesService } from '../domain/licenses.service';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { GetLicenseDto } from '../dto/get-license.dto';
import { I18nLang, I18nService } from 'nestjs-i18n';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiBody, ApiExcludeEndpoint, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('licenses')
@UseInterceptors(TransformInterceptor)
@UseGuards(AuthGuard)
@ApiTags('licenses')
@ApiBearerAuth()
export class LicensesController {
  constructor(private readonly licensesService: LicensesService, private readonly i18n: I18nService) {}

  @Get()
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Get users license',
  })
  @ApiBody({ type: GetLicenseDto })
  async getLicense(@Body() getLicenseDto: GetLicenseDto) {
    return await this.licensesService.getLicense(getLicenseDto);
  }

  @Get('check')
  @UsePipes(ValidationPipe)
  @ApiExcludeEndpoint()
  checkLicense(@Body() getLicenseDto: GetLicenseDto) {
    return { status: true };
  }

  @Get('translate')
  @UsePipes(ValidationPipe)
  @ApiExcludeEndpoint()
  async checkTest(@I18nLang() lang: string) {
    console.log(lang);
    return await this.i18n.translate('messages.subscription_3');
  }
}
