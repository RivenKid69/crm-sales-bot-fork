import {
  Body,
  ClassSerializerInterceptor,
  Controller,
  Delete,
  Get,
  NotFoundException,
  Post,
  Put,
  UseGuards,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { User } from '../../../common/decorators/user.decorator';
import { UsersService } from '../domain/users.service';
import { UpdateUserDto } from '../dto/update-user.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiBody, ApiExcludeEndpoint, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('user')
@UseInterceptors(TransformInterceptor)
@UseGuards(AuthGuard)
@ApiTags('users')
@ApiBearerAuth()
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  @Get()
  @UseInterceptors(ClassSerializerInterceptor)
  @ApiOperation({
    summary: 'Get user and users store',
  })
  async getUser(@User() user: UserDao) {
    return await this.usersService.getUserWithStore(user.id);
  }

  @Put()
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Update users info',
  })
  @ApiBody({
    type: UpdateUserDto,
  })
  async updateUser(@Body() updateUserDto: UpdateUserDto, @User() user: UserDao) {
    return await this.usersService.updateUser(updateUserDto, user);
  }

  @Delete()
  @ApiOperation({
    summary: 'Delete user',
  })
  async deleteUser(@User() user: UserDao) {
    return {
      status: true,
    };
  }

  // Указано, что данный метод устарел. Поставил на всякий случай, как заглушку
  @Post('certificate')
  @ApiExcludeEndpoint()
  async postCertificate() {
    throw new NotFoundException();
  }
}
