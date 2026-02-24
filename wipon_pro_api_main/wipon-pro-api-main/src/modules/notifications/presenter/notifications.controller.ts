import {
  Body,
  Controller,
  Delete,
  Get,
  Param,
  Post,
  Put,
  UseGuards,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { NotificationsService } from '../domain/notifications.service';
import { User } from '../../../common/decorators/user.decorator';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { UpdateNotificationStatusDto } from '../dto/update-notification-status.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiBody, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { SendNotificationDto } from '../dto/send-notification.dto';
import { MassNotificationDto } from '../dto/mass-notification.dto';

@Controller('notifications')
@UseInterceptors(TransformInterceptor)
@ApiTags('notifications')
export class NotificationsController {
  constructor(private readonly notificationsService: NotificationsService) {}

  @Get()
  @UseGuards(AuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary: 'Get users notifications',
  })
  async getUsersNotifications(@User() user: UserDao) {
    return await this.notificationsService.getUsersNotifications(user);
  }

  @Post()
  @UseGuards(AuthGuard)
  @UsePipes(ValidationPipe)
  sendNotification(@Body() sendNotificationDto: SendNotificationDto, @User() user: UserDao) {
    return this.notificationsService.sendNotification(sendNotificationDto, user);
  }

  @Put(':id')
  @UseGuards(AuthGuard)
  @ApiBearerAuth()
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Update users notification status',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  @ApiBody({ type: UpdateNotificationStatusDto })
  async updateNotificationStatus(
    @Param('id') notificationId: number,
    @Body() updateNfStatusDto: UpdateNotificationStatusDto,
    @User() user: UserDao,
  ) {
    return await this.notificationsService.updateNotificationStatus(notificationId, updateNfStatusDto, user.id);
  }

  @Delete(':id')
  @UseGuards(AuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary: 'Delete users notification permanently',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  async deleteUsersNotification(@Param('id') notificationId: number, @User() user: UserDao) {
    return await this.notificationsService.deleteUsersNotification(notificationId, user.id);
  }

  @Post('mass')
  @ApiOperation({
    summary: 'Send mass notification to users',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  sendMassNotificationToUsers(@Body() massNotificationDto: MassNotificationDto) {
    return this.notificationsService.sendMassNotificationToUsers(massNotificationDto);
  }
}
