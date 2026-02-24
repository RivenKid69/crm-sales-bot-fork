import { Controller, Get, Query, UseInterceptors } from '@nestjs/common';
import { versionResponseType } from '../../common/types/responses/version-response.type';
import { VersionService } from './domain/version.service';
import { TransformInterceptor } from '../../common/interceptor/transform.interceptor';
import { ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('version')
@ApiTags('version')
@UseInterceptors(TransformInterceptor)
export class VersionController {
  constructor(private readonly versionService: VersionService) {}
  @Get('mobile')
  @ApiOperation({
    summary: 'Get current mobile applications version',
  })
  getMobileVersion(@Query('version') versionOfUser: string): versionResponseType {
    return this.versionService.getMobileVersion(versionOfUser);
  }

  @Get('desktop')
  @ApiOperation({
    summary: 'Get current desktop applications version',
  })
  getDesktopVersion(@Query('version') versionOfUser: string): versionResponseType {
    return this.versionService.getDesktopVersion(versionOfUser);
  }
}
