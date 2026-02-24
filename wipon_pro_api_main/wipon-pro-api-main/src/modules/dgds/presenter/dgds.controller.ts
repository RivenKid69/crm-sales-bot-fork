import { Controller, Get, UseInterceptors } from '@nestjs/common';
import { DgdsService } from '../domain/dgds.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('dgds')
@UseInterceptors(TransformInterceptor)
@ApiTags('dgds')
export class DgdsController {
  constructor(private readonly dgdsService: DgdsService) {}

  @Get()
  @ApiOperation({
    summary: 'Returns Dgds list',
  })
  async getDgdsList() {
    return await this.dgdsService.getDgdsList();
  }
}
