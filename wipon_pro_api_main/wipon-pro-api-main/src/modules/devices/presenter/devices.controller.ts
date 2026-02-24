import { Body, Controller, Get, Post, UseGuards, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { DevicesService } from '../domain/devices.service';
import { AssignDeviceCodeDto } from '../dto/assign-device-code.dto';
import { User } from '../../../common/decorators/user.decorator';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { CheckDeviceDto } from '../dto/check-device.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiBody, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('devices')
@UseInterceptors(TransformInterceptor)
@UseGuards(AuthGuard)
@ApiBearerAuth()
@ApiTags('devices')
export class DevicesController {
  constructor(private readonly devicesService: DevicesService) {}

  @Post()
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Assign device code to user',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  @ApiBody({ type: AssignDeviceCodeDto })
  async assignDevice(@Body() assignDeviceCodeDto: AssignDeviceCodeDto, @User() user: UserDao) {
    return await this.devicesService.assignDeviceCode(assignDeviceCodeDto, user);
  }

  @Get('/check')
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Check users device',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: true } } },
  })
  @ApiBody({ type: CheckDeviceDto })
  async check(@Body() checkDeviceDto: CheckDeviceDto, @User() user: UserDao) {
    return await this.devicesService.checkUsersDevice(checkDeviceDto.application_type, user.id);
  }

  // @Get()
  // async test() {
  //   return await this.devicesService.test();
  // }
}
