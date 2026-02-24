import { Controller, Get } from '@nestjs/common';
import { ApiOkResponse, ApiOperation } from '@nestjs/swagger';

@Controller()
export class AppController {
  @ApiOperation({
    summary: 'Endpoint for testing is server working or not',
  })
  @Get('echo')
  echo() {
    return { status: 'success' };
  }
}
