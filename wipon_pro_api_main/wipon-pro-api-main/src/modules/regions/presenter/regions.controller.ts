import { Controller, Get, UseInterceptors } from '@nestjs/common';
import { RegionsService } from '../domain/regions.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('regions')
@UseInterceptors(TransformInterceptor)
@ApiTags('regions')
export class RegionsController {
  constructor(private readonly regionsService: RegionsService) {}

  @Get()
  @ApiOperation({
    summary: 'Returns available regions list',
  })
  async index() {
    return await this.regionsService.getRegionsList();
  }
}
