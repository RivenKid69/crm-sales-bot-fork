import { Body, Controller, Get, Query, UseInterceptors } from '@nestjs/common';
import { GetUgdsListDto } from '../dto/get-ugds-list.dto';
import { UgdsService } from '../domain/ugds.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBody, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('ugds')
@ApiTags('ugds')
@UseInterceptors(TransformInterceptor)
export class UgdsController {
  constructor(private readonly ugdsService: UgdsService) {}

  @Get()
  @ApiOperation({
    summary: 'Get Ugds List',
  })
  @ApiBody({ type: GetUgdsListDto })
  async getUgdsList(@Body() getUgdsDto: GetUgdsListDto, @Query('dgd_id') queryDgdId: string) {
    return await this.ugdsService.getUgdsList(getUgdsDto, queryDgdId);
  }
}
